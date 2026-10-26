"""Probe standard OpenTelemetry context, events and explicit thread propagation."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.metadata
import json
from pathlib import Path


def main():
    from opentelemetry import context
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    if args.output.exists():raise ValueError('Choose a new output')
    exporter=InMemorySpanExporter();provider=TracerProvider();provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer=provider.get_tracer('generic-reuse-audit')
    def worker(name,parent=None):
        token=context.attach(parent) if parent is not None else None
        try:
            with tracer.start_as_current_span(name):pass
        finally:
            if token is not None:context.detach(token)
    with tracer.start_as_current_span('request') as root:
        with tracer.start_as_current_span('handler') as child:
            child.add_event('cache.invalidate',{'owner':'session-A','key':'record-1'})
        parent=context.get_current()
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(worker,'thread_without_propagation').result()
            pool.submit(worker,'thread_with_propagation',parent).result()
    spans={s.name:s for s in exporter.get_finished_spans()};root=spans['request']
    checks=[{'case':'child_parent','passed':spans['handler'].parent.span_id==root.context.span_id},
        {'case':'explicit_thread_parent','passed':spans['thread_with_propagation'].parent.span_id==root.context.span_id},
        {'case':'thread_without_propagation_is_not_joined','passed':spans['thread_without_propagation'].parent is None},
        {'case':'state_event_attributes','passed':dict(spans['handler'].events[0].attributes)=={'owner':'session-A','key':'record-1'}}]
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'schema':'reuse-otel-sdk-audit/1','version':importlib.metadata.version('opentelemetry-sdk'),
        'input_origin':'authored_python_sdk_program','checks':checks,'product_instrumentation':False,
        'cpp_browser_rust_network_export_and_metrics_not_executed':True},indent=2),encoding='utf-8')
    provider.shutdown();print(json.dumps(checks))


if __name__=='__main__':main()
