package services

import (
	ocrpb    "temandifa-backend/internal/grpc/ocr"
	visionpb "temandifa-backend/internal/grpc/vision"
)

type VisionResult struct {
	Objects         []*visionpb.DetectionObject
	TotalDetected   int32
	InferenceTimeMs float32
	ServiceLevel    string
}

type OCRResult struct {
	Blocks          []*ocrpb.TextBlock
	FullText        string
	InferenceTimeMs float32
	ServiceLevel    string
	TextDetected    bool
}

type ASRResult struct {
	Text            string
	DetectedLang    string
	Confidence      float32
	InferenceTimeMs float32
	ServiceLevel    string
	Keywords        []string
}

type MultimodalResult struct {
	Vision *WorkerOutput `json:"vision,omitempty"`
	OCR    *WorkerOutput `json:"ocr,omitempty"`
	ASR    *WorkerOutput `json:"asr,omitempty"`
}

type WorkerOutput struct {
	Status          string      `json:"status"`
	Data            interface{} `json:"data,omitempty"`
	InferenceTimeMs float32     `json:"inference_time_ms,omitempty"`
	ErrorMessage    string      `json:"error,omitempty"`
}

type FallbackInput struct {
	RequestID         string
	TraceID           string
	Scenario          string
	Condition         string
	Run               int
	RequestedServices []string
	VisionResult      *VisionResult
	OCRResult         *OCRResult
	ASRResult         *ASRResult
	WorkerErrors      map[string]error
	CircuitStates     map[string]string
	WorkerStatuses    map[string]string
	FallbackEnabled   bool // true = treatment
}

type FallbackOutput struct {
	ResponseCategory ResponseCategory
	FallbackActive   bool
	FallbackReason   string
	DegradedServices []string
	Result           MultimodalResult
	InvalidReason    string
}

type FallbackEngine interface {
	Build(input FallbackInput) FallbackOutput
}

type fallbackEngine struct {
	classifier ResponseClassifier
}

func NewFallbackEngine(classifier ResponseClassifier) FallbackEngine {
	return &fallbackEngine{classifier: classifier}
}

// Build menerapkan matriks fallback:
//   - treatment: worker gagal → partial jika ada hasil valid
//   - baseline: worker gagal → failure langsung
func (f *fallbackEngine) Build(input FallbackInput) FallbackOutput {
	result := MultimodalResult{}
	var workerResults []WorkerResult
	var degraded []string

	for _, svc := range input.RequestedServices {
		switch svc {
		case "vision":
			wo, wr := buildVisionOutput(svc, input.VisionResult, input.WorkerErrors[svc])
			result.Vision = &wo
			workerResults = append(workerResults, wr)
			if wr.Status != WorkerStatusSuccess {
				degraded = append(degraded, svc)
			}

		case "ocr":
			wo, wr := buildOCROutput(svc, input.OCRResult, input.WorkerErrors[svc])
			result.OCR = &wo
			workerResults = append(workerResults, wr)
			if wr.Status != WorkerStatusSuccess {
				degraded = append(degraded, svc)
			}

		case "asr":
			wo, wr := buildASROutput(svc, input.ASRResult, input.WorkerErrors[svc])
			result.ASR = &wo
			workerResults = append(workerResults, wr)
			if wr.Status != WorkerStatusSuccess {
				degraded = append(degraded, svc)
			}
		}
	}

	fallbackReason := ""
	if len(degraded) > 0 {
		if len(degraded) == len(input.RequestedServices) {
			fallbackReason = "all_workers_unavailable"
		} else {
			fallbackReason = degraded[0] + "_worker_unavailable"
		}
	}

	fallbackActive := len(degraded) > 0 && input.FallbackEnabled

	classification := f.classifier.Classify(ClassificationInput{
		RequestedServices: input.RequestedServices,
		WorkerResults:     workerResults,
		FallbackActive:    fallbackActive,
		FallbackReason:    fallbackReason,
		Condition:         input.Condition,
		AllowPartial:      input.FallbackEnabled,
		FallbackEnabled:   input.FallbackEnabled,
	})

	return FallbackOutput{
		ResponseCategory: classification.Category,
		FallbackActive:   fallbackActive,
		FallbackReason:   fallbackReason,
		DegradedServices: classification.DegradedServices,
		Result:           result,
		InvalidReason:    classification.InvalidReason,
	}
}

func buildVisionOutput(svc string, res *VisionResult, err error) (WorkerOutput, WorkerResult) {
	if err != nil || res == nil {
		return WorkerOutput{Status: "unavailable", ErrorMessage: errMsg(err)},
			WorkerResult{Service: svc, Status: WorkerStatusUnavailable, Err: err}
	}
	type visionData struct {
		Objects         []*visionpb.DetectionObject `json:"objects"`
		TotalDetected   int32                       `json:"total_detected"`
		InferenceTimeMs float32                     `json:"inference_time_ms"`
	}
	return WorkerOutput{
			Status:          "success",
			InferenceTimeMs: res.InferenceTimeMs,
			Data:            visionData{Objects: res.Objects, TotalDetected: res.TotalDetected, InferenceTimeMs: res.InferenceTimeMs},
		},
		WorkerResult{Service: svc, Status: WorkerStatusSuccess, Data: res}
}

func buildOCROutput(svc string, res *OCRResult, err error) (WorkerOutput, WorkerResult) {
	if err != nil || res == nil {
		return WorkerOutput{Status: "unavailable", ErrorMessage: errMsg(err)},
			WorkerResult{Service: svc, Status: WorkerStatusUnavailable, Err: err}
	}
	type ocrData struct {
		FullText        string           `json:"full_text"`
		Blocks          []*ocrpb.TextBlock `json:"blocks"`
		TextDetected    bool             `json:"text_detected"`
		InferenceTimeMs float32          `json:"inference_time_ms"`
	}
	return WorkerOutput{
			Status:          "success",
			InferenceTimeMs: res.InferenceTimeMs,
			Data:            ocrData{FullText: res.FullText, Blocks: res.Blocks, TextDetected: res.TextDetected, InferenceTimeMs: res.InferenceTimeMs},
		},
		WorkerResult{Service: svc, Status: WorkerStatusSuccess, Data: res}
}

func buildASROutput(svc string, res *ASRResult, err error) (WorkerOutput, WorkerResult) {
	if err != nil || res == nil {
		return WorkerOutput{Status: "unavailable", ErrorMessage: errMsg(err)},
			WorkerResult{Service: svc, Status: WorkerStatusUnavailable, Err: err}
	}
	type asrData struct {
		Text            string   `json:"text"`
		DetectedLang    string   `json:"detected_language"`
		Confidence      float32  `json:"confidence"`
		Keywords        []string `json:"keywords"`
		InferenceTimeMs float32  `json:"inference_time_ms"`
	}
	return WorkerOutput{
			Status:          "success",
			InferenceTimeMs: res.InferenceTimeMs,
			Data:            asrData{Text: res.Text, DetectedLang: res.DetectedLang, Confidence: res.Confidence, Keywords: res.Keywords, InferenceTimeMs: res.InferenceTimeMs},
		},
		WorkerResult{Service: svc, Status: WorkerStatusSuccess, Data: res}
}

func errMsg(err error) string {
	if err == nil {
		return ""
	}
	return err.Error()
}
