package services

import (
	"sync"
	"time"

	"go.uber.org/zap"

	"temandifa-backend/internal/logger"
)

type CBState string

const (
	CBClosed   CBState = "CLOSED"
	CBOpen     CBState = "OPEN"
	CBHalfOpen CBState = "HALF_OPEN"
)

type CircuitBreakerConfig struct {
	MaxFailures  int
	ResetTimeout time.Duration
	MaxTrials    int
}

type CircuitBreaker struct {
	name        string
	config      CircuitBreakerConfig
	state       CBState
	failures    int
	trials      int
	lastFailure time.Time
	mu          sync.Mutex
}

func NewCircuitBreaker(name string, config CircuitBreakerConfig) *CircuitBreaker {
	return &CircuitBreaker{
		name:   name,
		config: config,
		state:  CBClosed,
	}
}

func (cb *CircuitBreaker) Allow() bool {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	switch cb.state {
	case CBClosed:
		return true
	case CBOpen:
		if time.Since(cb.lastFailure) > cb.config.ResetTimeout {
			cb.state = CBHalfOpen
			cb.trials = 0
			logger.Info("Circuit breaker transitioning to HALF_OPEN", zap.String("name", cb.name))
			return true
		}
		return false
	case CBHalfOpen:
		if cb.trials < cb.config.MaxTrials {
			cb.trials++
			return true
		}
		return false
	}
	return false
}

func (cb *CircuitBreaker) RecordSuccess() {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	if cb.state != CBClosed {
		logger.Info("Circuit breaker transitioning to CLOSED", zap.String("name", cb.name))
	}
	cb.failures = 0
	cb.trials = 0
	cb.state = CBClosed
}

func (cb *CircuitBreaker) RecordFailure() {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	// Jangan perbarui lastFailure saat sudah OPEN — timer ResetTimeout harus
	// terus berjalan agar Allow() bisa transisi ke HALF_OPEN setelah timeout.
	// Tanpa guard ini, health check yang memanggil RecordFailure() setiap interval
	// akan terus me-reset timer dan membuat CB terjebak OPEN selamanya.
	if cb.state == CBOpen {
		return
	}

	cb.lastFailure = time.Now()

	// Saat half-open, satu kegagalan langsung kembali ke open.
	// Early return mencegah concurrent RecordFailure (dari trial lain yang juga gagal)
	// jatuh ke cabang failures++ saat state sudah CBOpen.
	if cb.state == CBHalfOpen {
		cb.trials = 0
		cb.state = CBOpen
		logger.Warn("Circuit breaker transitioning back to OPEN from HALF_OPEN", zap.String("name", cb.name))
		return
	}

	if cb.state == CBClosed {
		cb.failures++
		if cb.failures >= cb.config.MaxFailures {
			logger.Warn("Circuit breaker transitioning to OPEN",
				zap.String("name", cb.name),
				zap.Int("failures", cb.failures),
			)
			cb.state = CBOpen
		}
	}
}

func (cb *CircuitBreaker) State() CBState {
	cb.mu.Lock()
	defer cb.mu.Unlock()
	return cb.state
}

func (cb *CircuitBreaker) FailureRatio() float64 {
	cb.mu.Lock()
	defer cb.mu.Unlock()
	if cb.config.MaxFailures == 0 {
		return 0
	}
	r := float64(cb.failures) / float64(cb.config.MaxFailures)
	if r > 1 {
		return 1
	}
	return r
}
