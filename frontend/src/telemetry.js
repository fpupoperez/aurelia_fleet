/** Browser traces. Batches go to the API, which forwards them to Langfuse. The browser never sees the keys. */
import { trace } from "@opentelemetry/api";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { Resource } from "@opentelemetry/resources";
import { BatchSpanProcessor } from "@opentelemetry/sdk-trace-base";
import { WebTracerProvider } from "@opentelemetry/sdk-trace-web";

const provider = new WebTracerProvider({
  resource: new Resource({ "service.name": "aurelia-frontend" }),
  spanProcessors: [
    new BatchSpanProcessor(
      new OTLPTraceExporter({
        url: `${window.location.origin}/api/v1/otel/v1/traces`,
      }),
    ),
  ],
});

provider.register();

export const tracer = trace.getTracer("aurelia-frontend");

/** W3C traceparent for the active span, sent on API calls so the UI and the API share one trace. */
export function traceparent() {
  const span = trace.getActiveSpan();
  if (!span) {
    return null;
  }
  const context = span.spanContext();
  if (!context.traceId) {
    return null;
  }
  const flags = context.traceFlags.toString(16).padStart(2, "0");
  return `00-${context.traceId}-${context.spanId}-${flags}`;
}
