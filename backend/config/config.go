package config

import (
	"errors"
	"fmt"
	"os"
	"time"

	"temandifa-backend/internal/logger"

	"github.com/spf13/viper"
	"go.uber.org/zap"
)

const (
	ExperimentModeStaticResilience = "static_resilience"
	ExperimentModeTreatment        = "treatment"
	ExperimentModeAblationBaseline = "baseline" // backward compatibility only
)

type Config struct {
	Port         string
	GinMode      string
	ReadTimeout  time.Duration
	WriteTimeout time.Duration

	DatabaseDSN string

	DBMaxOpenConns    int
	DBMaxIdleConns    int
	DBConnMaxLifetime time.Duration
	DBConnMaxIdleTime time.Duration

	AllowedOrigins string

	RedisAddr        string
	RedisPassword    string
	RedisPoolSize    int
	RedisMinIdleConn int
	RedisMaxRetries  int

	JWTSecret              string
	JWTAccessTokenDuration time.Duration

	// RefreshTokenHMACSecret digunakan sebagai kunci HMAC-SHA256 untuk hashing
	// refresh token di database. Jika kosong, fallback ke JWTSecret.
	// Gunakan secret terpisah agar rotasi JWT_SECRET tidak membatalkan semua sesi aktif.
	RefreshTokenHMACSecret string

	AIVisionHTTPAddr string
	AIOCRHTTPAddr    string
	AISpeechHTTPAddr string

	AIVisionGRPCAddr string
	AIOCRGRPCAddr    string
	AISpeechGRPCAddr string

	RateLimitRequests int
	RateLimitWindow   int

	AIRateLimitRequests int
	AIRateLimitWindow   int

	AIDetectTimeout     time.Duration
	AIOCRTimeout        time.Duration
	AITranscribeTimeout time.Duration

	HealthCheckInterval time.Duration
	FallbackStateTTL    time.Duration

	MaxBodySize int64

	TrustedProxies string

	MetricsToken string

	AIGrpcTLS   bool
	AIGrpcToken string

	AIGrpcCAFile string

	AIGrpcServerName string

	AIOCRLanguage string
	SentryDSN     string

	ExperimentServiceEmail string

	ExperimentMode     string
	ExperimentScenario string
	ExperimentRun      int

	EnableStaticResilience bool
	EnableRAMAResilience   bool

	EnableTimeout        bool
	EnableRetry          bool
	EnableCircuitBreaker bool
	EnableHealthCheck    bool

	EnableContextAwareFallback      bool
	EnableComputeProfileAwarePolicy bool
	EnableFallbackCoordination      bool
	EnablePartialResponse           bool

	EnableResponseClassifier bool
	EnableExperimentLogging  bool
	EnableExperimentMetrics  bool

	EnableAICacheExperiment bool

	RequestTimeoutSeconds int
	AIMultimodalTimeout   time.Duration

	StaticTimeoutSeconds        int
	StaticRetryMaxAttempts      int
	StaticRetryBackoffMs        int
	StaticCBFailureThreshold    int
	StaticCBResetTimeoutSeconds int
	StaticCBHalfOpenMaxRequests int

	RAMADefaultTimeoutSeconds int
	RAMACBFailureThreshold    int
	RAMACBResetTimeoutSeconds int
	RAMACBHalfOpenMaxRequests int
}

func LoadConfig() (*Config, error) {
	viper.SetDefault("PORT", "8080")
	viper.SetDefault("GIN_MODE", "debug")
	viper.SetDefault("READ_TIMEOUT", "30s")
	viper.SetDefault("WRITE_TIMEOUT", "60s")
	viper.SetDefault("REDIS_ADDR", "localhost:6379")
	viper.SetDefault("RATE_LIMIT_REQUESTS", 60)
	viper.SetDefault("RATE_LIMIT_WINDOW", 60)
	viper.SetDefault("MAX_BODY_SIZE", 50*1024*1024)
	viper.SetDefault("TRUSTED_PROXIES", "127.0.0.1")

	viper.SetDefault("DB_MAX_OPEN_CONNS", 25)
	viper.SetDefault("DB_MAX_IDLE_CONNS", 5)
	viper.SetDefault("DB_CONN_MAX_LIFETIME", "5m")
	viper.SetDefault("DB_CONN_MAX_IDLE_TIME", "5m")

	viper.SetDefault("REDIS_POOL_SIZE", 20)
	viper.SetDefault("REDIS_MIN_IDLE_CONNS", 5)
	viper.SetDefault("REDIS_MAX_RETRIES", 3)

	viper.SetDefault("AI_VISION_HTTP_ADDR", "http://localhost:8001")
	viper.SetDefault("AI_OCR_HTTP_ADDR", "http://localhost:8002")
	viper.SetDefault("AI_SPEECH_HTTP_ADDR", "http://localhost:8003")
	viper.SetDefault("AI_VISION_GRPC_ADDR", "localhost:50051")
	viper.SetDefault("AI_OCR_GRPC_ADDR", "localhost:50052")
	viper.SetDefault("AI_SPEECH_GRPC_ADDR", "localhost:50053")

	viper.SetDefault("AI_RATE_LIMIT_REQUESTS", 10)
	viper.SetDefault("AI_RATE_LIMIT_WINDOW", 60)

	viper.SetDefault("AI_DETECT_TIMEOUT", "30s")
	viper.SetDefault("AI_OCR_TIMEOUT", "45s")
	viper.SetDefault("AI_TRANSCRIBE_TIMEOUT", "60s")

	viper.SetDefault("HEALTH_CHECK_INTERVAL", "15s")
	viper.SetDefault("FALLBACK_STATE_TTL", "300s")

	viper.SetDefault("EXPERIMENT_MODE", ExperimentModeTreatment)
	viper.SetDefault("EXPERIMENT_SCENARIO", "SS")
	viper.SetDefault("EXPERIMENT_RUN", 1)

	viper.SetDefault("ENABLE_STATIC_RESILIENCE", false)
	viper.SetDefault("ENABLE_RAMA_RESILIENCE", true)

	viper.SetDefault("ENABLE_TIMEOUT", true)
	viper.SetDefault("ENABLE_RETRY", true)
	viper.SetDefault("ENABLE_CIRCUIT_BREAKER", true)
	viper.SetDefault("ENABLE_HEALTH_CHECK", true)

	viper.SetDefault("ENABLE_CONTEXT_AWARE_FALLBACK", true)
	viper.SetDefault("ENABLE_COMPUTE_PROFILE_AWARE_POLICY", true)
	viper.SetDefault("ENABLE_FALLBACK_COORDINATION", true)
	viper.SetDefault("ENABLE_PARTIAL_RESPONSE", true)

	viper.SetDefault("ENABLE_RESPONSE_CLASSIFIER", true)
	viper.SetDefault("ENABLE_EXPERIMENT_LOGGING", false)
	viper.SetDefault("ENABLE_EXPERIMENT_METRICS", false)
	viper.SetDefault("ENABLE_AI_CACHE_EXPERIMENT", true)

	viper.SetDefault("REQUEST_TIMEOUT_SECONDS", 90)
	viper.SetDefault("AI_MULTIMODAL_TIMEOUT", "90s")

	viper.SetDefault("STATIC_TIMEOUT_SECONDS", 90)
	viper.SetDefault("STATIC_RETRY_MAX_ATTEMPTS", 1)
	viper.SetDefault("STATIC_RETRY_BACKOFF_MS", 250)
	viper.SetDefault("STATIC_CB_FAILURE_THRESHOLD", 5)
	viper.SetDefault("STATIC_CB_RESET_TIMEOUT_SECONDS", 30)
	viper.SetDefault("STATIC_CB_HALF_OPEN_MAX_REQUESTS", 3)

	viper.SetDefault("RAMA_DEFAULT_TIMEOUT_SECONDS", 90)
	viper.SetDefault("RAMA_CB_FAILURE_THRESHOLD", 5)
	viper.SetDefault("RAMA_CB_RESET_TIMEOUT_SECONDS", 30)
	viper.SetDefault("RAMA_CB_HALF_OPEN_MAX_REQUESTS", 3)

	viper.SetConfigFile(".env")
	viper.SetConfigType("env")

	if err := viper.ReadInConfig(); err != nil {
		var notFound viper.ConfigFileNotFoundError
		if errors.As(err, &notFound) || os.IsNotExist(err) {
			logger.Info("No .env file found, relying on environment variables")
		} else {
			return nil, fmt.Errorf("error reading .env file: %w", err)
		}
	} else {
		logger.Info("Configuration loaded from .env file")
	}

	viper.AutomaticEnv()

	cfg := &Config{
		Port:         viper.GetString("PORT"),
		GinMode:      viper.GetString("GIN_MODE"),
		ReadTimeout:  viper.GetDuration("READ_TIMEOUT"),
		WriteTimeout: viper.GetDuration("WRITE_TIMEOUT"),

		DatabaseDSN:       viper.GetString("DB_DSN"),
		DBMaxOpenConns:    viper.GetInt("DB_MAX_OPEN_CONNS"),
		DBMaxIdleConns:    viper.GetInt("DB_MAX_IDLE_CONNS"),
		DBConnMaxLifetime: viper.GetDuration("DB_CONN_MAX_LIFETIME"),
		DBConnMaxIdleTime: viper.GetDuration("DB_CONN_MAX_IDLE_TIME"),

		AllowedOrigins: viper.GetString("ALLOWED_ORIGINS"),

		RedisAddr:        viper.GetString("REDIS_ADDR"),
		RedisPassword:    viper.GetString("REDIS_PASSWORD"),
		RedisPoolSize:    viper.GetInt("REDIS_POOL_SIZE"),
		RedisMinIdleConn: viper.GetInt("REDIS_MIN_IDLE_CONNS"),
		RedisMaxRetries:  viper.GetInt("REDIS_MAX_RETRIES"),

		JWTSecret:              viper.GetString("JWT_SECRET"),
		RefreshTokenHMACSecret: viper.GetString("REFRESH_TOKEN_HMAC_SECRET"),
		JWTAccessTokenDuration: func() time.Duration {
			if d, err := time.ParseDuration(viper.GetString("JWT_ACCESS_TOKEN_DURATION")); err == nil && d > 0 {
				return d
			}
			return 15 * time.Minute
		}(),

		AIVisionHTTPAddr: viper.GetString("AI_VISION_HTTP_ADDR"),
		AIOCRHTTPAddr:    viper.GetString("AI_OCR_HTTP_ADDR"),
		AISpeechHTTPAddr: viper.GetString("AI_SPEECH_HTTP_ADDR"),
		AIVisionGRPCAddr: viper.GetString("AI_VISION_GRPC_ADDR"),
		AIOCRGRPCAddr:    viper.GetString("AI_OCR_GRPC_ADDR"),
		AISpeechGRPCAddr: viper.GetString("AI_SPEECH_GRPC_ADDR"),

		RateLimitRequests:   viper.GetInt("RATE_LIMIT_REQUESTS"),
		RateLimitWindow:     viper.GetInt("RATE_LIMIT_WINDOW"),
		AIRateLimitRequests: viper.GetInt("AI_RATE_LIMIT_REQUESTS"),
		AIRateLimitWindow:   viper.GetInt("AI_RATE_LIMIT_WINDOW"),

		AIDetectTimeout:     viper.GetDuration("AI_DETECT_TIMEOUT"),
		AIOCRTimeout:        viper.GetDuration("AI_OCR_TIMEOUT"),
		AITranscribeTimeout: viper.GetDuration("AI_TRANSCRIBE_TIMEOUT"),

		HealthCheckInterval: viper.GetDuration("HEALTH_CHECK_INTERVAL"),
		FallbackStateTTL:    viper.GetDuration("FALLBACK_STATE_TTL"),

		MaxBodySize: viper.GetInt64("MAX_BODY_SIZE"),

		TrustedProxies:   viper.GetString("TRUSTED_PROXIES"),
		MetricsToken:     viper.GetString("METRICS_TOKEN"),
		AIGrpcTLS:        viper.GetBool("AI_GRPC_TLS"),
		AIGrpcToken:      viper.GetString("AI_GRPC_TOKEN"),
		AIGrpcCAFile:     viper.GetString("AI_GRPC_CA_FILE"),
		AIGrpcServerName: viper.GetString("AI_GRPC_SERVER_NAME"),
		AIOCRLanguage:    viper.GetString("AI_OCR_LANGUAGE"),
		SentryDSN:        viper.GetString("SENTRY_DSN"),

		ExperimentServiceEmail: viper.GetString("EXPERIMENT_EMAIL"),

		ExperimentMode:     viper.GetString("EXPERIMENT_MODE"),
		ExperimentScenario: viper.GetString("EXPERIMENT_SCENARIO"),
		ExperimentRun:      viper.GetInt("EXPERIMENT_RUN"),

		EnableStaticResilience: viper.GetBool("ENABLE_STATIC_RESILIENCE"),
		EnableRAMAResilience:   viper.GetBool("ENABLE_RAMA_RESILIENCE"),

		EnableTimeout:        viper.GetBool("ENABLE_TIMEOUT"),
		EnableRetry:          viper.GetBool("ENABLE_RETRY"),
		EnableCircuitBreaker: viper.GetBool("ENABLE_CIRCUIT_BREAKER"),
		EnableHealthCheck:    viper.GetBool("ENABLE_HEALTH_CHECK"),

		EnableContextAwareFallback:      viper.GetBool("ENABLE_CONTEXT_AWARE_FALLBACK"),
		EnableComputeProfileAwarePolicy: viper.GetBool("ENABLE_COMPUTE_PROFILE_AWARE_POLICY"),
		EnableFallbackCoordination:      viper.GetBool("ENABLE_FALLBACK_COORDINATION"),
		EnablePartialResponse:           viper.GetBool("ENABLE_PARTIAL_RESPONSE"),

		EnableResponseClassifier: viper.GetBool("ENABLE_RESPONSE_CLASSIFIER"),
		EnableExperimentLogging:  viper.GetBool("ENABLE_EXPERIMENT_LOGGING"),
		EnableExperimentMetrics:  viper.GetBool("ENABLE_EXPERIMENT_METRICS"),
		EnableAICacheExperiment:  viper.GetBool("ENABLE_AI_CACHE_EXPERIMENT"),

		RequestTimeoutSeconds: viper.GetInt("REQUEST_TIMEOUT_SECONDS"),
		AIMultimodalTimeout:   viper.GetDuration("AI_MULTIMODAL_TIMEOUT"),

		StaticTimeoutSeconds:        viper.GetInt("STATIC_TIMEOUT_SECONDS"),
		StaticRetryMaxAttempts:      viper.GetInt("STATIC_RETRY_MAX_ATTEMPTS"),
		StaticRetryBackoffMs:        viper.GetInt("STATIC_RETRY_BACKOFF_MS"),
		StaticCBFailureThreshold:    viper.GetInt("STATIC_CB_FAILURE_THRESHOLD"),
		StaticCBResetTimeoutSeconds: viper.GetInt("STATIC_CB_RESET_TIMEOUT_SECONDS"),
		StaticCBHalfOpenMaxRequests: viper.GetInt("STATIC_CB_HALF_OPEN_MAX_REQUESTS"),

		RAMADefaultTimeoutSeconds: viper.GetInt("RAMA_DEFAULT_TIMEOUT_SECONDS"),
		RAMACBFailureThreshold:    viper.GetInt("RAMA_CB_FAILURE_THRESHOLD"),
		RAMACBResetTimeoutSeconds: viper.GetInt("RAMA_CB_RESET_TIMEOUT_SECONDS"),
		RAMACBHalfOpenMaxRequests: viper.GetInt("RAMA_CB_HALF_OPEN_MAX_REQUESTS"),
	}

	if err := cfg.Validate(); err != nil {
		return nil, err
	}

	return cfg, nil
}

func (c *Config) Validate() error {
	if c.DatabaseDSN == "" {
		return fmt.Errorf("DB_DSN diperlukan")
	}

	if c.JWTSecret == "" {
		return fmt.Errorf("JWT_SECRET diperlukan")
	}
	if len(c.JWTSecret) < 32 {
		return fmt.Errorf("JWT_SECRET minimal 32 karakter untuk keamanan")
	}
	if len(c.JWTSecret) < 64 {
		logger.Warn("JWT_SECRET kurang dari 64 karakter — disarankan minimal 64 karakter untuk produksi")
	}

	if c.GinMode == "release" && c.AllowedOrigins == "" {
		logger.Warn("ALLOWED_ORIGINS tidak dikonfigurasi di mode production — semua CORS request akan ditolak. Set ALLOWED_ORIGINS=<origin1,origin2> untuk mengaktifkan akses dari klien.")
	}

	if c.GinMode == "release" && c.AIGrpcToken == "" {
		return fmt.Errorf("AI_GRPC_TOKEN diperlukan di mode release")
	}
	if c.GinMode == "release" && c.AIGrpcToken != "" && !c.AIGrpcTLS {
		// Tidak di-fatal-error karena deployment VPS menggunakan gRPC di jaringan
		// internal (VPC private) tanpa TLS. Tetap tampilkan peringatan agar operator
		// tahu jika konfigurasi ini tidak sengaja di jaringan publik.
		logger.Warn("AI_GRPC_TLS=false saat AI_GRPC_TOKEN dikonfigurasi di mode release — token dikirim tanpa enkripsi transport. Aman hanya untuk jaringan internal yang terisolasi.")
	}

	if c.RateLimitRequests <= 0 {
		return fmt.Errorf("RATE_LIMIT_REQUESTS harus > 0, dapat: %d", c.RateLimitRequests)
	}
	if c.AIRateLimitRequests <= 0 {
		return fmt.Errorf("AI_RATE_LIMIT_REQUESTS harus > 0, dapat: %d", c.AIRateLimitRequests)
	}
	if c.MaxBodySize <= 0 {
		return fmt.Errorf("MAX_BODY_SIZE harus > 0")
	}
	if c.AIDetectTimeout <= 0 || c.AIOCRTimeout <= 0 || c.AITranscribeTimeout <= 0 {
		return fmt.Errorf("AI timeout values harus > 0")
	}
	if c.EnableStaticResilience && c.EnableRetry {
		if c.StaticRetryMaxAttempts <= 0 {
			return fmt.Errorf("STATIC_RETRY_MAX_ATTEMPTS harus > 0 (%d)", c.StaticRetryMaxAttempts)
		}
		if c.StaticRetryMaxAttempts > 10 {
			return fmt.Errorf("STATIC_RETRY_MAX_ATTEMPTS terlalu besar (%d) — maksimal 10 untuk menghindari penumpukan goroutine saat fault injection", c.StaticRetryMaxAttempts)
		}
	}
	if c.AIMultimodalTimeout <= 0 {
		return fmt.Errorf("AI_MULTIMODAL_TIMEOUT harus > 0")
	}

	if err := c.validateExperimentMode(); err != nil {
		return err
	}

	logger.Info("RAMA experiment configuration",
		zap.String("experiment_mode", c.ExperimentMode),
		zap.String("scenario", c.ExperimentScenario),
		zap.Int("run", c.ExperimentRun),
		zap.Bool("static_resilience", c.EnableStaticResilience),
		zap.Bool("rama_resilience", c.EnableRAMAResilience),
		zap.Bool("circuit_breaker", c.EnableCircuitBreaker),
		zap.Bool("context_aware_fallback", c.EnableContextAwareFallback),
		zap.Bool("partial_response", c.EnablePartialResponse),
		zap.Bool("response_classifier", c.EnableResponseClassifier),
		zap.Bool("experiment_logging", c.EnableExperimentLogging),
	)

	logger.Info("Configuration loaded successfully",
		zap.String("port", c.Port),
		zap.String("mode", c.GinMode),
		zap.String("vision_grpc", c.AIVisionGRPCAddr),
		zap.String("ocr_grpc", c.AIOCRGRPCAddr),
		zap.String("speech_grpc", c.AISpeechGRPCAddr),
	)

	return nil
}

// validateExperimentMode memvalidasi konsistensi konfigurasi eksperimen saat startup.
// Backend gagal startup (fatal) jika konfigurasi tidak konsisten — ini mencegah
// data eksperimen yang tidak valid masuk ke dataset.
func (c *Config) validateExperimentMode() error {
	switch c.ExperimentMode {
	case ExperimentModeStaticResilience:
		if !c.EnableStaticResilience {
			return fmt.Errorf("invalid static_resilience configuration: ENABLE_STATIC_RESILIENCE must be true")
		}
		if c.EnableRAMAResilience {
			return fmt.Errorf("invalid static_resilience configuration: ENABLE_RAMA_RESILIENCE must be false")
		}
		if !c.EnableTimeout {
			return fmt.Errorf("invalid static_resilience configuration: ENABLE_TIMEOUT must be true")
		}
		if !c.EnableRetry {
			return fmt.Errorf("invalid static_resilience configuration: ENABLE_RETRY must be true")
		}
		if !c.EnableCircuitBreaker {
			return fmt.Errorf("invalid static_resilience configuration: ENABLE_CIRCUIT_BREAKER must be true")
		}
		if c.EnableContextAwareFallback {
			return fmt.Errorf("invalid static_resilience configuration: context-aware fallback must be disabled")
		}
		if c.EnableComputeProfileAwarePolicy {
			return fmt.Errorf("invalid static_resilience configuration: compute-profile-aware policy must be disabled")
		}
		if c.EnableFallbackCoordination {
			return fmt.Errorf("invalid static_resilience configuration: fallback coordination must be disabled")
		}
		if c.EnablePartialResponse {
			return fmt.Errorf("invalid static_resilience configuration: partial response must be disabled")
		}

	case ExperimentModeTreatment:
		if !c.EnableRAMAResilience {
			return fmt.Errorf("invalid treatment configuration: ENABLE_RAMA_RESILIENCE must be true")
		}
		if !c.EnableContextAwareFallback {
			return fmt.Errorf("invalid treatment configuration: ENABLE_CONTEXT_AWARE_FALLBACK must be true")
		}
		if !c.EnableComputeProfileAwarePolicy {
			return fmt.Errorf("invalid treatment configuration: ENABLE_COMPUTE_PROFILE_AWARE_POLICY must be true")
		}
		if !c.EnableFallbackCoordination {
			return fmt.Errorf("invalid treatment configuration: ENABLE_FALLBACK_COORDINATION must be true")
		}
		if !c.EnablePartialResponse {
			return fmt.Errorf("invalid treatment configuration: ENABLE_PARTIAL_RESPONSE must be true")
		}
		if !c.EnableCircuitBreaker {
			return fmt.Errorf("invalid treatment configuration: ENABLE_CIRCUIT_BREAKER must be true")
		}

	case ExperimentModeAblationBaseline:
		// Backward compatibility: tidak divalidasi ketat
		logger.Warn("ExperimentMode 'baseline' digunakan — mode ini hanya untuk debugging, bukan eksperimen final")

	default:
		return fmt.Errorf("EXPERIMENT_MODE tidak valid: %q (pilih: static_resilience, treatment)", c.ExperimentMode)
	}

	return nil
}
