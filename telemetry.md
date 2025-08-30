# Claude Code Telemetry Documentation

## Setup
For setting up Claude Code telemetry, follow the official quick start guide:
https://docs.anthropic.com/en/docs/claude-code/monitoring-usage#quick-start

## Current Configuration
Telemetry is configured in `~/.zshrc` with:
- Host: `10.18.1.1`
- Port: `4317`
- Protocol: gRPC/OTLP

### Environment Variables
```bash
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_METRICS_EXPORTER=otlp
export OTEL_LOGS_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_PROTOCOL=grpc
export OTEL_EXPORTER_OTLP_ENDPOINT=http://10.18.1.1:4317
export OTEL_METRIC_EXPORT_INTERVAL=10000
export OTEL_LOGS_EXPORT_INTERVAL=5000
```

## OpenTelemetry Backend Setup

### Working Docker Stack
For collecting Claude Code telemetry, use the **ColeMurray/claude-code-otel** Docker stack:

```bash
# Clone the repository
git clone https://github.com/ColeMurray/claude-code-otel.git
cd claude-code-otel

# Start the stack
docker-compose up -d
```

This stack includes:
- **OpenTelemetry Collector** (ports 4317 for gRPC, 4318 for HTTP)
- **Prometheus** for metrics storage
- **Loki** for logs storage
- **Grafana** for visualization (port 3000, admin/admin)

### Why This Stack?
The ColeMurray/claude-code-otel stack is specifically configured for Claude Code telemetry with:
- Proper OTLP receiver configuration for gRPC and HTTP
- Prometheus exporter in the metrics pipeline
- Resource processor for attribute enrichment
- Pre-configured Grafana dashboards for Claude Code metrics

### Note on Alternative Stacks
The generic `grafana/docker-otel-lgtm` stack may not properly handle Claude Code metrics without additional configuration. The ColeMurray stack has been tested and confirmed to work with Claude Code's metric format.

## Metrics Reference
For complete documentation on Claude Code telemetry metrics, see:
https://docs.anthropic.com/en/docs/claude-code/monitoring-usage#standard-attributes