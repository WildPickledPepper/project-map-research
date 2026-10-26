"""Adapt native compiler arguments for clangd without executing command text."""
import json
import os
from pathlib import Path
import shlex


def command_arguments(command):
    if not isinstance(command, str) or not command.strip():
        raise ValueError('Compilation command must be a nonempty string')
    if os.name != 'nt':
        return shlex.split(command)
    # Use Windows' command-line parser rather than a second shell interpreter.
    import ctypes
    from ctypes import wintypes
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    kernel.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel.LocalFree.restype = wintypes.HLOCAL
    count = ctypes.c_int()
    values = shell.CommandLineToArgvW(command, ctypes.byref(count))
    if not values:
        raise ValueError('Windows could not parse the native compilation command')
    try:
        return [values[i] for i in range(count.value)]
    finally:
        kernel.LocalFree(ctypes.cast(values, wintypes.HLOCAL))


def with_builtin_headers(database, output, headers):
    """Prefer clang's bundled builtin headers over GCC's query-driver headers."""
    database, output, headers = Path(database), Path(output), Path(headers).resolve()
    if database.is_dir():
        database = database / 'compile_commands.json'
    if not headers.is_dir():
        raise ValueError('Clang builtin header directory is missing')
    rows = json.loads(database.read_text(encoding='utf-8-sig'))
    if not isinstance(rows, list):
        raise ValueError('Expected a native compilation database array')
    adjusted = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('file'), str) or not isinstance(row.get('directory'), str):
            raise ValueError('Native compilation rows need file and directory')
        args = row.get('arguments')
        if args is None:
            args = command_arguments(row.get('command'))
        if not isinstance(args, list) or not args or not all(isinstance(a, str) for a in args):
            raise ValueError('Native compiler arguments must be a nonempty string array')
        result = {k: v for k, v in row.items() if k != 'command'}
        result['arguments'] = [args[0], '-isystem', str(headers), *args[1:]]
        adjusted.append(result)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'compile_commands.json').write_text(json.dumps(adjusted), encoding='utf-8')
    return {'status': 'applied', 'policy': 'clang_builtin_headers_before_query_driver_headers',
            'native_entries': len(adjusted), 'source_database_modified': False,
            'command_text_executed': False}
