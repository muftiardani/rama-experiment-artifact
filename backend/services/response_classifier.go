package services

import "temandifa-backend/internal/config"

type ResponseCategory string

const (
	ResponseFull    ResponseCategory = "full"
	ResponsePartial ResponseCategory = "partial"
	ResponseFailure ResponseCategory = "failure"
)

const InvalidStaticBaselinePartial = "INVALID_STATIC_BASELINE_PARTIAL"

type WorkerResultStatus string

const (
	WorkerStatusSuccess     WorkerResultStatus = "success"
	WorkerStatusUnavailable WorkerResultStatus = "unavailable"
	WorkerStatusTimeout     WorkerResultStatus = "timeout"
	WorkerStatusCircuitOpen WorkerResultStatus = "circuit_open"
	WorkerStatusError       WorkerResultStatus = "error"
)

type WorkerResult struct {
	Service string
	Status  WorkerResultStatus
	Data    any
	Err     error
}

type ClassificationInput struct {
	RequestedServices []string
	WorkerResults     []WorkerResult
	FallbackActive    bool
	FallbackReason    string
	Condition         string
	AllowPartial      bool
	FallbackEnabled   bool
	ClassifierEnabled bool
}

type ClassificationOutput struct {
	Category         ResponseCategory
	DegradedServices []string
	FailureReason    string
	InvalidReason string
}

type ResponseClassifier interface {
	Classify(input ClassificationInput) ClassificationOutput
}

type responseClassifier struct{}

func NewResponseClassifier() ResponseClassifier {
	return &responseClassifier{}
}

// Classify menerapkan aturan klasifikasi RAMA:
//
//   - full     : semua worker yang diminta sukses
//   - partial  : sebagian gagal, fallback aktif (treatment only)
//   - failure  : semua gagal, atau fallback tidak aktif (static_resilience), atau timeout total
//
// Aturan khusus SRB: jika kondisi static_resilience menghasilkan partial,
// kategori dioverride ke failure dan InvalidReason diisi INVALID_STATIC_BASELINE_PARTIAL.
func (r *responseClassifier) Classify(input ClassificationInput) ClassificationOutput {
	if len(input.RequestedServices) == 0 {
		return ClassificationOutput{
			Category:      ResponseFailure,
			FailureReason: "no_services_requested",
		}
	}

	successCount := 0
	var degraded []string

	resultMap := make(map[string]WorkerResultStatus, len(input.WorkerResults))
	for _, wr := range input.WorkerResults {
		resultMap[wr.Service] = wr.Status
	}

	for _, svc := range input.RequestedServices {
		st, ok := resultMap[svc]
		if ok && st == WorkerStatusSuccess {
			successCount++
		} else {
			degraded = append(degraded, svc)
		}
	}

	total := len(input.RequestedServices)

	var out ClassificationOutput

	switch {
	case successCount == total:
		out = ClassificationOutput{
			Category:         ResponseFull,
			DegradedServices: []string{},
		}

	case successCount > 0 && input.FallbackActive && input.FallbackEnabled && input.AllowPartial:
		out = ClassificationOutput{
			Category:         ResponsePartial,
			DegradedServices: degraded,
			FailureReason:    input.FallbackReason,
		}

	default:
		reason := input.FallbackReason
		if reason == "" {
			if successCount == 0 {
				reason = "all_workers_failed"
			} else {
				reason = "fallback_disabled"
			}
		}
		out = ClassificationOutput{
			Category:         ResponseFailure,
			DegradedServices: degraded,
			FailureReason:    reason,
		}
	}

	// SRB tidak boleh menghasilkan partial response.
	// Jika terjadi, tandai run sebagai invalid.
	if out.Category == ResponsePartial &&
		(input.Condition == config.ExperimentModeStaticResilience ||
			input.Condition == config.ExperimentModeAblationBaseline) {
		out.Category = ResponseFailure
		out.InvalidReason = InvalidStaticBaselinePartial
		if out.FailureReason == "" {
			out.FailureReason = "fallback_disabled"
		}
	}

	return out
}
