package services

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"

	"temandifa-backend/internal/clients"
	"temandifa-backend/internal/config"
	ocrpb "temandifa-backend/internal/grpc/ocr"
	speechpb "temandifa-backend/internal/grpc/speech"
	visionpb "temandifa-backend/internal/grpc/vision"
	"temandifa-backend/internal/logger"
	"temandifa-backend/internal/metrics"

	"go.uber.org/zap"
)

type WorkerStatus string

const (
	StatusHealthy   WorkerStatus = "HEALTHY"
	StatusDegraded  WorkerStatus = "DEGRADED"
	StatusUnhealthy WorkerStatus = "UNHEALTHY"
)

type FallbackLevel int

const (
	LevelFull     FallbackLevel = 0
	LevelDegraded FallbackLevel = 1
	LevelMinimal  FallbackLevel = 2
	LevelFallback FallbackLevel = 3
)

type SystemState struct {
	VisionStatus WorkerStatus  `json:"vision_status"`
	OCRStatus    WorkerStatus  `json:"ocr_status"`
	SpeechStatus WorkerStatus  `json:"speech_status"`
	VisionLevel  FallbackLevel `json:"vision_level"`
	OCRLevel     FallbackLevel `json:"ocr_level"`
	SpeechLevel  FallbackLevel `json:"speech_level"`
	LastUpdated  time.Time     `json:"last_updated"`
}

const systemStateKey = "temandifa:system_state"

type OrchestratorService struct {
	clients             *clients.AIClients
	redis               *redis.Client
	visionCB            *CircuitBreaker
	ocrCB               *CircuitBreaker
	speechCB            *CircuitBreaker
	healthCheckInterval time.Duration
	cancel              context.CancelFunc
	done                chan struct{}
	startMu             sync.Mutex
	started             bool
	cbEnabled           bool
	experimentMode      string
}

func NewOrchestratorService(c *clients.AIClients, rdb *redis.Client, cfg *config.Config) *OrchestratorService {
	failureThreshold := cfg.StaticCBFailureThreshold
	resetTimeoutSec := cfg.StaticCBResetTimeoutSeconds
	halfOpenMax := cfg.StaticCBHalfOpenMaxRequests
	if cfg.ExperimentMode == config.ExperimentModeTreatment {
		failureThreshold = cfg.RAMACBFailureThreshold
		resetTimeoutSec = cfg.RAMACBResetTimeoutSeconds
		halfOpenMax = cfg.RAMACBHalfOpenMaxRequests
	}
	if failureThreshold <= 0 {
		failureThreshold = 5
	}
	if resetTimeoutSec <= 0 {
		resetTimeoutSec = 30
	}
	if halfOpenMax <= 0 {
		halfOpenMax = 3
	}

	cbConfig := CircuitBreakerConfig{
		MaxFailures:  failureThreshold,
		ResetTimeout: time.Duration(resetTimeoutSec) * time.Second,
		MaxTrials:    halfOpenMax,
	}
	interval := cfg.HealthCheckInterval
	if interval <= 0 {
		interval = 15 * time.Second
	}
	return &OrchestratorService{
		clients:             c,
		redis:               rdb,
		visionCB:            NewCircuitBreaker("vision", cbConfig),
		ocrCB:               NewCircuitBreaker("ocr", cbConfig),
		speechCB:            NewCircuitBreaker("speech", cbConfig),
		healthCheckInterval: interval,
		cbEnabled:           cfg.EnableCircuitBreaker,
		experimentMode:      cfg.ExperimentMode,
	}
}

// Start menjalankan background health check cycle dan menyimpan cancel func.
// Idempotent: panggilan kedua diabaikan tanpa membocorkan goroutine.
func (o *OrchestratorService) Start() {
	o.startMu.Lock()
	defer o.startMu.Unlock()
	if o.started {
		return
	}
	ctx, cancel := context.WithCancel(context.Background())
	o.cancel = cancel
	o.done = make(chan struct{})
	o.started = true
	go o.HealthCheckCycle(ctx)
}

func (o *OrchestratorService) Stop() {
	o.startMu.Lock()
	if o.cancel == nil {
		o.startMu.Unlock()
		return
	}
	o.cancel()
	o.cancel = nil
	o.started = false
	done := o.done
	o.startMu.Unlock()

	if done != nil {
		select {
		case <-done:
		case <-time.After(10 * time.Second):
		}
	}
}

func (o *OrchestratorService) HealthCheckCycle(ctx context.Context) {
	defer func() {
		o.startMu.Lock()
		if o.done != nil {
			close(o.done)
		}
		o.startMu.Unlock()
	}()

	ticker := time.NewTicker(o.healthCheckInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			o.evaluateAndUpdateState(ctx)
		}
	}
}

func (o *OrchestratorService) evaluateAndUpdateState(ctx context.Context) {
	if o.clients == nil {
		return
	}

	type workerResult struct {
		name   string
		status WorkerStatus
	}

	workers := []string{"vision", "ocr", "speech"}
	results := make(chan workerResult, len(workers))

	var wg sync.WaitGroup
	for _, w := range workers {
		wg.Add(1)
		w := w
		go func() {
			defer wg.Done()
			results <- workerResult{name: w, status: o.checkWorker(ctx, w)}
		}()
	}
	wg.Wait()
	close(results)

	state := SystemState{LastUpdated: time.Now()}
	for r := range results {
		switch r.name {
		case "vision":
			state.VisionStatus = r.status
			state.VisionLevel = o.statusToFallbackLevel(r.status)
			o.updateCircuitBreaker(o.visionCB, r.status)
		case "ocr":
			state.OCRStatus = r.status
			state.OCRLevel = o.statusToFallbackLevel(r.status)
			o.updateCircuitBreaker(o.ocrCB, r.status)
		case "speech":
			state.SpeechStatus = r.status
			state.SpeechLevel = o.statusToFallbackLevel(r.status)
			o.updateCircuitBreaker(o.speechCB, r.status)
		}
	}

	if err := o.saveState(ctx, state); err != nil {
		logger.Error("Failed to save system state", zap.Error(err))
	}

	logger.Info("Health check completed",
		zap.String("vision", string(state.VisionStatus)),
		zap.String("ocr", string(state.OCRStatus)),
		zap.String("speech", string(state.SpeechStatus)),
	)
}

func (o *OrchestratorService) checkWorker(ctx context.Context, worker string) WorkerStatus {
	timeoutCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	var (
		statusStr string
		err       error
	)
	switch worker {
	case "vision":
		resp, e := o.clients.Vision.HealthCheck(timeoutCtx, &visionpb.HealthRequest{})
		err = e
		if resp != nil {
			statusStr = resp.Status
		}
	case "ocr":
		resp, e := o.clients.OCR.HealthCheck(timeoutCtx, &ocrpb.HealthRequest{})
		err = e
		if resp != nil {
			statusStr = resp.Status
		}
	case "speech":
		resp, e := o.clients.Speech.HealthCheck(timeoutCtx, &speechpb.HealthRequest{})
		err = e
		if resp != nil {
			statusStr = resp.Status
		}
	default:
		return StatusUnhealthy
	}

	if err != nil {
		logger.Warn("Worker health check failed",
			zap.String("worker", worker), zap.Error(err))
		return StatusUnhealthy
	}

	switch WorkerStatus(statusStr) {
	case StatusHealthy, StatusDegraded, StatusUnhealthy:
		return WorkerStatus(statusStr)
	default:
		// Status yang tidak dikenal dari worker dianggap UNHEALTHY (fail-safe),
		// bukan HEALTHY, untuk menghindari false positive.
		logger.Warn("Worker returned unknown status",
			zap.String("worker", worker),
			zap.String("status", statusStr),
		)
		return StatusUnhealthy
	}
}

func (o *OrchestratorService) statusToFallbackLevel(s WorkerStatus) FallbackLevel {
	switch s {
	case StatusHealthy:
		return LevelFull
	case StatusDegraded:
		return LevelDegraded
	case StatusUnhealthy:
		return LevelFallback
	default:
		return LevelFallback
	}
}

func (o *OrchestratorService) GetCurrentState(ctx context.Context) (SystemState, error) {
	data, err := o.redis.Get(ctx, systemStateKey).Bytes()
	if err == redis.Nil {
		// Belum ada state di Redis (belum ada health check yang selesai).
		// Default ke UNHEALTHY agar sistem fail-safe selama startup window.
		return SystemState{
			VisionStatus: StatusUnhealthy,
			OCRStatus:    StatusUnhealthy,
			SpeechStatus: StatusUnhealthy,
		}, nil
	}
	if err != nil {
		return SystemState{}, fmt.Errorf("redis get state: %w", err)
	}
	var state SystemState
	if err := json.Unmarshal(data, &state); err != nil {
		return SystemState{}, err
	}
	return state, nil
}

func (o *OrchestratorService) saveState(ctx context.Context, state SystemState) error {
	data, err := json.Marshal(state)
	if err != nil {
		return err
	}
	return o.redis.Set(ctx, systemStateKey, data, 5*time.Minute).Err()
}

func (o *OrchestratorService) updateCircuitBreaker(cb *CircuitBreaker, status WorkerStatus) {
	// Health checks hanya mencatat kegagalan — mereka mengkonfirmasi worker down tetapi
	// tidak boleh me-reset breaker yang dibuka oleh kegagalan request nyata.
	// Pemulihan (OPEN→HALF_OPEN→CLOSED) didorong oleh Allow() setelah ResetTimeout,
	// lalu oleh RecordWorkerSuccess dari request nyata yang berhasil.
	if status == StatusUnhealthy {
		cb.RecordFailure()
	}
	metrics.UpdateCircuitBreakerState(cb.name, cbStateToInt(cb.State()))
}

func cbStateToInt(s CBState) int {
	switch s {
	case CBClosed:
		return 0
	case CBOpen:
		return 1
	case CBHalfOpen:
		return 2
	default:
		return 0
	}
}

func cbStateName(s CBState) string {
	switch s {
	case CBClosed:
		return "closed"
	case CBOpen:
		return "open"
	case CBHalfOpen:
		return "half_open"
	default:
		return "unknown"
	}
}

// IsWorkerAvailable mengecek apakah circuit breaker worker mengizinkan request.
// Jika cbEnabled=false (mode baseline), selalu return true — bypass CB.
func (o *OrchestratorService) IsWorkerAvailable(worker string) bool {
	if !o.cbEnabled {
		return true
	}
	switch worker {
	case "vision":
		return o.visionCB.Allow()
	case "ocr":
		return o.ocrCB.Allow()
	case "speech":
		return o.speechCB.Allow()
	default:
		return false
	}
}

func (o *OrchestratorService) RecordWorkerSuccess(worker string) {
	var cb *CircuitBreaker
	switch worker {
	case "vision":
		cb = o.visionCB
	case "ocr":
		cb = o.ocrCB
	case "speech":
		cb = o.speechCB
	}
	if cb != nil {
		prevState := cb.State()
		cb.RecordSuccess()
		metrics.CircuitBreakerRequests.WithLabelValues(cb.name, cbStateName(prevState), "success").Inc()
		metrics.CircuitBreakerFailureRatio.WithLabelValues(cb.name).Set(cb.FailureRatio())
		metrics.UpdateCircuitBreakerState(cb.name, cbStateToInt(cb.State()))
	}
}

func (o *OrchestratorService) RecordWorkerFailure(worker string) {
	var cb *CircuitBreaker
	switch worker {
	case "vision":
		cb = o.visionCB
	case "ocr":
		cb = o.ocrCB
	case "speech":
		cb = o.speechCB
	}
	if cb != nil {
		prevState := cb.State()
		cb.RecordFailure()
		metrics.CircuitBreakerRequests.WithLabelValues(cb.name, cbStateName(prevState), "failure").Inc()
		metrics.CircuitBreakerFailureRatio.WithLabelValues(cb.name).Set(cb.FailureRatio())
		metrics.UpdateCircuitBreakerState(cb.name, cbStateToInt(cb.State()))
	}
}

func (o *OrchestratorService) GetWorkerCircuitBreakerStates() map[string]CBState {
	return map[string]CBState{
		"vision": o.visionCB.State(),
		"ocr":    o.ocrCB.State(),
		"speech": o.speechCB.State(),
	}
}

func (o *OrchestratorService) GetWorkerCBStateInts() map[string]int {
	return map[string]int{
		"vision": cbStateToInt(o.visionCB.State()),
		"ocr":    cbStateToInt(o.ocrCB.State()),
		"speech": cbStateToInt(o.speechCB.State()),
	}
}
