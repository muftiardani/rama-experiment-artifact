package services

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"time"

	"github.com/goccy/go-json"
	"go.uber.org/zap"
	"golang.org/x/sync/singleflight"
	"google.golang.org/grpc/status"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"

	"temandifa-backend/internal/cache"
	"temandifa-backend/internal/clients"
	"temandifa-backend/internal/config"
	"temandifa-backend/internal/constants"
	apperrors "temandifa-backend/internal/errors"
	ocrpb "temandifa-backend/internal/grpc/ocr"
	speechpb "temandifa-backend/internal/grpc/speech"
	visionpb "temandifa-backend/internal/grpc/vision"
	"temandifa-backend/internal/logger"
)

var ErrAIInvalidArgument = errors.New("AI worker invalid argument")

// ErrAIPermanent digunakan untuk error non-transient yang tidak boleh di-retry.
// CB tetap mencatat kegagalan ErrAIPermanent agar circuit breaker merespons
// gangguan deployment (UNAUTHENTICATED) dan crash worker (INTERNAL).
// Hanya ErrAIInvalidArgument (input client buruk) yang tidak dicatat ke CB.
var ErrAIPermanent = errors.New("AI worker permanent failure")

type AIWorkerOps interface {
	DetectObjects(ctx context.Context, imageData []byte, confidenceThreshold float32) (*visionpb.DetectResponse, error)
	RecognizeText(ctx context.Context, imageData []byte, language string, includeCoords bool) (*ocrpb.OCRResponse, error)
	Transcribe(ctx context.Context, audioData []byte, language string, keywordOnly bool) (*speechpb.TranscribeResponse, error)
}

type AIService interface {
	DetectObjects(ctx context.Context, fileContent []byte, filename string) (*visionpb.DetectResponse, bool, error)
	ExtractText(ctx context.Context, fileContent []byte, filename string, lang string) (*ocrpb.OCRResponse, bool, error)
	TranscribeAudio(ctx context.Context, fileContent []byte, filename string, lang string) (*speechpb.TranscribeResponse, bool, error)
}

type aiService struct {
	grpcClient       AIWorkerOps
	cacheService     CacheService
	orchestrator     *OrchestratorService
	requestGroup     singleflight.Group
	cacheEnabled     bool
	retryEnabled     bool
	retryBackoffMs   int
	retryMaxAttempts int
}

func NewAIService(grpcClient *clients.AIClients, cacheService CacheService, orch *OrchestratorService, cfg *config.Config) AIService {
	// Assign nil interface correctly: assigning a typed-nil *clients.AIClients directly
	// to the AIWorkerOps interface field would produce a non-nil interface (Go spec),
	// making nil checks inside methods always false and causing a nil-deref panic.
	var ops AIWorkerOps
	if grpcClient != nil {
		ops = grpcClient
	}
	cacheEnabled := true
	retryEnabled := false
	retryBackoffMs := 250
	retryMaxAttempts := 1
	if cfg != nil {
		cacheEnabled = cfg.EnableAICacheExperiment
		// Static retry aktif hanya pada kondisi SRB (ENABLE_RETRY && ENABLE_STATIC_RESILIENCE)
		retryEnabled = cfg.EnableRetry && cfg.EnableStaticResilience
		if cfg.StaticRetryBackoffMs > 0 {
			retryBackoffMs = cfg.StaticRetryBackoffMs
		}
		if cfg.StaticRetryMaxAttempts > 0 {
			retryMaxAttempts = cfg.StaticRetryMaxAttempts
		}
	}
	if retryEnabled && cacheEnabled {
		// Retry loop berada di dalam blok `if !s.cacheEnabled`, sehingga tidak
		// pernah dieksekusi saat cache aktif. Catat sebagai peringatan agar operator
		// menyadari konfigurasi yang tidak konsisten.
		logger.Warn("ENABLE_RETRY=true tetapi ENABLE_AI_CACHE_EXPERIMENT=true: retry loop tidak aktif selama cache diaktifkan")
	}
	return &aiService{
		grpcClient:       ops,
		cacheService:     cacheService,
		orchestrator:     orch,
		cacheEnabled:     cacheEnabled,
		retryEnabled:     retryEnabled,
		retryBackoffMs:   retryBackoffMs,
		retryMaxAttempts: retryMaxAttempts,
	}
}

// withRequestID menempel request_id dari originalCtx ke detachedCtx sebagai gRPC outgoing metadata
// sehingga worker dapat mencatat request_id yang sama untuk korelasi log lintas service.
func withRequestID(detachedCtx, originalCtx context.Context) context.Context {
	if rid, ok := originalCtx.Value(constants.RequestIDKey).(string); ok && rid != "" {
		return metadata.AppendToOutgoingContext(detachedCtx, "x-request-id", rid)
	}
	return detachedCtx
}

// inheritDeadline returns a context derived from background that inherits parent's
// deadline (if any) but not its cancellation signal. This prevents a canceled HTTP
// request context from aborting in-flight singleflight work that other waiters
// depend on, while still bounding execution to the original route timeout.
func inheritDeadline(parent context.Context) (context.Context, context.CancelFunc) {
	if deadline, ok := parent.Deadline(); ok {
		return context.WithDeadline(context.Background(), deadline)
	}
	return context.WithTimeout(context.Background(), 5*time.Minute)
}

func (s *aiService) waitBeforeRetry(ctx context.Context) bool {
	timer := time.NewTimer(time.Duration(s.retryBackoffMs) * time.Millisecond)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return false
	case <-timer.C:
		return true
	}
}

func (s *aiService) shouldRetry(attempt int, err error) bool {
	return err != nil && s.retryEnabled && attempt < s.retryMaxAttempts &&
		!errors.Is(err, ErrAIInvalidArgument) &&
		!errors.Is(err, ErrAIPermanent)
}

func (s *aiService) DetectObjects(ctx context.Context, fileContent []byte, filename string) (*visionpb.DetectResponse, bool, error) {
	if s.grpcClient == nil {
		return nil, false, apperrors.ErrAIService
	}
	if s.orchestrator != nil && !s.orchestrator.IsWorkerAvailable("vision") {
		return nil, false, apperrors.ErrAIService
	}

	cacheKey := s.cacheService.GenerateKey("detect", fileContent)

	if s.cacheEnabled {
		if cachedBytes, hit := s.cacheService.Get(ctx, cacheKey); hit {
			var resp visionpb.DetectResponse
			if err := json.Unmarshal(cachedBytes, &resp); err == nil {
				return &resp, true, nil
			}
		}
	}

	detachedCtx, detachedCancel := inheritDeadline(ctx)
	detachedCtx = withRequestID(detachedCtx, ctx)
	defer detachedCancel()

	workerFailureRecorded := false
	doDetect := func() (*visionpb.DetectResponse, error) {
		resp, err := s.grpcClient.DetectObjects(detachedCtx, fileContent, 0.5)
		if err != nil {
			mappedErr := s.handleError(err)
			if errors.Is(mappedErr, ErrAIInvalidArgument) {
				return nil, mappedErr
			}
			// Record CB failure sekali per request untuk semua error worker lain,
			// termasuk ErrAIPermanent, agar circuit breaker merespons degradasi akurat.
			if s.orchestrator != nil && !workerFailureRecorded {
				s.orchestrator.RecordWorkerFailure("vision")
				workerFailureRecorded = true
			}
			return nil, mappedErr
		}
		if s.orchestrator != nil {
			s.orchestrator.RecordWorkerSuccess("vision")
			workerFailureRecorded = false
		}
		if s.cacheEnabled {
			if jsonBytes, err := json.Marshal(resp); err == nil {
				// Gunakan detachedCtx agar cache write tidak dibatalkan saat HTTP
				// client disconnect — konteksnya sudah terputus dari cancellation HTTP.
				s.cacheService.SetAsync(detachedCtx, cacheKey, jsonBytes, cache.Config.DetectionTTL)
			}
		}
		return resp, nil
	}

	// Saat cache dinonaktifkan (eksperimen), skip singleflight agar setiap request
	// benar-benar memanggil worker (tidak dibagi dengan request concurrent lain).
	if !s.cacheEnabled {
		resp, err := doDetect()
		for attempt := 0; s.shouldRetry(attempt, err); attempt++ {
			if !s.waitBeforeRetry(detachedCtx) {
				err = context.DeadlineExceeded
				break
			}
			resp, err = doDetect()
		}
		return resp, false, err
	}

	v, err, shared := s.requestGroup.Do(cacheKey, func() (interface{}, error) {
		return doDetect()
	})

	if err != nil {
		return nil, false, err
	}

	if shared {
		logger.DebugCtx(ctx, "Request singleflight dibagi (shared)", zap.String("key", cacheKey))
	}

	return v.(*visionpb.DetectResponse), shared, nil
}

func (s *aiService) ExtractText(ctx context.Context, fileContent []byte, filename string, lang string) (*ocrpb.OCRResponse, bool, error) {
	if s.grpcClient == nil {
		return nil, false, apperrors.ErrAIService
	}
	if s.orchestrator != nil && !s.orchestrator.IsWorkerAvailable("ocr") {
		return nil, false, apperrors.ErrAIService
	}

	// Hash fileContent terlebih dahulu agar cache key tidak perlu alokasi buffer sebesar file.
	contentHash := sha256.Sum256(fileContent)
	cacheKey := s.cacheService.GenerateKey("ocr", append(contentHash[:], lang...))

	if s.cacheEnabled {
		if cachedBytes, hit := s.cacheService.Get(ctx, cacheKey); hit {
			var resp ocrpb.OCRResponse
			if err := json.Unmarshal(cachedBytes, &resp); err == nil {
				return &resp, true, nil
			}
		}
	}

	detachedCtx, detachedCancel := inheritDeadline(ctx)
	detachedCtx = withRequestID(detachedCtx, ctx)
	defer detachedCancel()

	workerFailureRecorded := false
	doOCR := func() (*ocrpb.OCRResponse, error) {
		resp, err := s.grpcClient.RecognizeText(detachedCtx, fileContent, lang, false)
		if err != nil {
			mappedErr := s.handleError(err)
			if errors.Is(mappedErr, ErrAIInvalidArgument) {
				return nil, mappedErr
			}
			if s.orchestrator != nil && !workerFailureRecorded {
				s.orchestrator.RecordWorkerFailure("ocr")
				workerFailureRecorded = true
			}
			return nil, mappedErr
		}
		if s.orchestrator != nil {
			s.orchestrator.RecordWorkerSuccess("ocr")
			workerFailureRecorded = false
		}
		if s.cacheEnabled {
			if jsonBytes, err := json.Marshal(resp); err == nil {
				s.cacheService.SetAsync(detachedCtx, cacheKey, jsonBytes, cache.Config.OCRTTL)
			}
		}
		return resp, nil
	}

	if !s.cacheEnabled {
		resp, err := doOCR()
		for attempt := 0; s.shouldRetry(attempt, err); attempt++ {
			if !s.waitBeforeRetry(detachedCtx) {
				err = context.DeadlineExceeded
				break
			}
			resp, err = doOCR()
		}
		return resp, false, err
	}

	v, err, shared := s.requestGroup.Do(cacheKey, func() (interface{}, error) {
		return doOCR()
	})

	if err != nil {
		return nil, false, err
	}

	if shared {
		logger.DebugCtx(ctx, "Request singleflight dibagi (shared)", zap.String("key", cacheKey))
	}

	return v.(*ocrpb.OCRResponse), shared, nil
}

func (s *aiService) TranscribeAudio(ctx context.Context, fileContent []byte, filename string, lang string) (*speechpb.TranscribeResponse, bool, error) {
	if s.grpcClient == nil {
		return nil, false, apperrors.ErrAIService
	}
	if s.orchestrator != nil && !s.orchestrator.IsWorkerAvailable("speech") {
		return nil, false, apperrors.ErrAIService
	}

	contentHash := sha256.Sum256(fileContent)
	cacheKey := s.cacheService.GenerateKey("transcribe", append(contentHash[:], lang...))

	if s.cacheEnabled {
		if cachedBytes, hit := s.cacheService.Get(ctx, cacheKey); hit {
			var resp speechpb.TranscribeResponse
			if err := json.Unmarshal(cachedBytes, &resp); err == nil {
				return &resp, true, nil
			}
		}
	}

	detachedCtx, detachedCancel := inheritDeadline(ctx)
	detachedCtx = withRequestID(detachedCtx, ctx)
	defer detachedCancel()

	workerFailureRecorded := false
	doTranscribe := func() (*speechpb.TranscribeResponse, error) {
		resp, err := s.grpcClient.Transcribe(detachedCtx, fileContent, lang, false)
		if err != nil {
			mappedErr := s.handleError(err)
			if errors.Is(mappedErr, ErrAIInvalidArgument) {
				return nil, mappedErr
			}
			if s.orchestrator != nil && !workerFailureRecorded {
				s.orchestrator.RecordWorkerFailure("speech")
				workerFailureRecorded = true
			}
			return nil, mappedErr
		}
		if s.orchestrator != nil {
			s.orchestrator.RecordWorkerSuccess("speech")
			workerFailureRecorded = false
		}
		if s.cacheEnabled {
			if jsonBytes, err := json.Marshal(resp); err == nil {
				s.cacheService.SetAsync(detachedCtx, cacheKey, jsonBytes, cache.Config.TranscriptionTTL)
			}
		}
		return resp, nil
	}

	if !s.cacheEnabled {
		resp, err := doTranscribe()
		for attempt := 0; s.shouldRetry(attempt, err); attempt++ {
			if !s.waitBeforeRetry(detachedCtx) {
				err = context.DeadlineExceeded
				break
			}
			resp, err = doTranscribe()
		}
		return resp, false, err
	}

	v, err, shared := s.requestGroup.Do(cacheKey, func() (interface{}, error) {
		return doTranscribe()
	})

	if err != nil {
		return nil, false, err
	}

	if shared {
		logger.DebugCtx(ctx, "Request singleflight dibagi (shared)", zap.String("key", cacheKey))
	}

	return v.(*speechpb.TranscribeResponse), shared, nil
}

func (s *aiService) handleError(err error) error {
	if errors.Is(err, context.DeadlineExceeded) {
		return context.DeadlineExceeded
	}

	st, ok := status.FromError(err)
	if ok {
		logger.Error("AI Worker gRPC failed",
			zap.String("code", st.Code().String()),
			zap.String("message", st.Message()),
		)
		if st.Code() == codes.DeadlineExceeded {
			return context.DeadlineExceeded
		}
		if st.Code() == codes.InvalidArgument {
			return fmt.Errorf("%w: %s", ErrAIInvalidArgument, st.Message())
		}
		if st.Code() == codes.Unauthenticated || st.Code() == codes.PermissionDenied {
			return fmt.Errorf("%w: %s", ErrAIPermanent, st.Message())
		}
		if st.Code() == codes.ResourceExhausted {
			// Worker antrian penuh — retry memperparah beban; CB tetap mencatat kegagalan.
			return fmt.Errorf("%w: %s", ErrAIPermanent, st.Message())
		}
		// codes.Internal tidak dipetakan ke ErrAIPermanent — bisa merupakan crash
		// transient (OOM kill, proxy restart) yang bisa berhasil setelah retry.
		// CB tetap mencatat kegagalan ini melalui path normal di atasnya.
		return fmt.Errorf("AI Worker error: %s", st.Message())
	}

	logger.Error("AI Worker call failed", zap.Error(err))
	return err
}
