"""Host and installed-runtime checks; no checkpoint loading or downloads."""
import argparse
import importlib
import importlib.metadata
import json
import platform
from pathlib import Path
import sys

from .profiles import load_profile


def host_info():
    libc, version = platform.libc_ver()
    return {'os': platform.system(), 'architecture': platform.machine(),
              'python': platform.python_version(), 'libc': libc, 'libc_version': version}


def check_host(profile):
    report = host_info()
    libc, version = report['libc'], report['libc_version']
    if report['os'] != 'Linux' or sys.version_info[:2] != (3, 12):
        raise RuntimeError('ACTOR_HOST_UNSUPPORTED: use Linux Python 3.12, not native Windows')
    if report['architecture'] not in ('x86_64', 'aarch64'):
        raise RuntimeError('ACTOR_ARCH_UNSUPPORTED: no selected NVIDIA wheel for this architecture')
    if profile['vllm_version'] == '0.19.1':
        if libc != 'glibc' or tuple(int(p) for p in version.split('.')[:2]) < (2, 31):
            raise RuntimeError('ACTOR_GLIBC_UNSUPPORTED: vLLM 0.19.1 wheels require glibc >= 2.31; '
                               'use an approved newer Linux container/node, not an implicit source build')
    return report


def check_runtime(profile, gpu=False):
    report = check_host(profile)
    report['packages'] = {}
    for package in ('vllm', 'transformers'):
        installed = importlib.metadata.version(package)
        report['packages'][package] = installed
        if installed != profile[package + '_version']:
            raise RuntimeError('PROFILE_PACKAGE_MISMATCH: ' + package)
    torch = importlib.import_module('torch')
    importlib.import_module('vllm._C')
    parsers = importlib.import_module('vllm.tool_parsers')
    parsers.ToolParserManager.get_tool_parser(profile['tool_call_parser'])
    report.update(torch=torch.__version__, torch_cuda=torch.version.cuda, gpu_checked=False)
    if gpu:
        if not torch.cuda.is_available():
            raise RuntimeError('ACTOR_CUDA_UNAVAILABLE: check the allocated GPU and NVIDIA driver')
        if profile['dtype'] == 'bfloat16' and not torch.cuda.is_bf16_supported():
            raise RuntimeError('ACTOR_PRECISION_UNSUPPORTED: bfloat16 is unavailable')
        dtype = torch.bfloat16 if profile['dtype'] == 'bfloat16' else torch.float16
        value = torch.ones((8, 8), device='cuda', dtype=dtype)
        if not bool(torch.isfinite(value @ value).all().item()):
            raise RuntimeError('ACTOR_CUDA_KERNEL_FAILED')
        torch.cuda.synchronize()
        report.update(gpu_checked=True, gpu=torch.cuda.get_device_name(),
                      capability=list(torch.cuda.get_device_capability()))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True, type=Path)
    parser.add_argument('--gpu', action='store_true', help='Run a tiny CUDA operation inside a GPU allocation')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    report = {**host_info(), 'status': 'failed', 'scope': 'runtime preflight, not model/tool-call validation'}
    try:
        report.update(check_runtime(load_profile(args.profile), args.gpu), status='passed')
    except Exception as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2)
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'passed' else 1
