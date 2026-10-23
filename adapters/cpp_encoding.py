"""Win32 encoding output buffers; source wrappers keep their own identities."""
import re

from adapters.cpp_transmission import value
from adapters.syntax_supplement import text, walk


class EncodingBuffers:
    FUNCTIONS = {'MultiByteToWideChar': (6, 'wchar_t'), 'WideCharToMultiByte': (8, 'char')}

    def __init__(self, engine):
        self.engine = engine

    def external(self, spelling, node, info):
        x = self.engine.x; name = spelling.removeprefix('::')
        if name not in self.FUNCTIONS: return False
        visible = x.visibility.get(info['path'], {info['path']})
        if not any(i[0].lower() in {'windows.h', 'stringapiset.h'} for p in visible for i in x.units[p]['includes']): return False
        if not spelling.startswith('::') and x.variables(name, node, info['path'], info['uid']): return False
        # Source declarations, members and macros can shadow the SDK symbol.
        if any(f['path'] in visible and f['signature'][0].split('::')[-1] == name for f in x.functions_by_id.values()): return False
        return not any(n.type in {'preproc_def', 'preproc_function_def'} and text(n.child_by_field_name('name')) == name
                       for p in visible for n in walk(x.units[p]['tree'].root_node))

    def call(self, spelling, node, actuals, receiver, method, state, info, context):
        e = self.engine; conditions = state['conditions']
        allocated = re.fullmatch(r'std::make_unique\s*<\s*(char|wchar_t)\s*\[\s*\]\s*>', spelling)
        if allocated and len(actuals) == 1:
            return value('encoding_buffer_owner', spelling='std::unique_ptr<' + allocated[1] + '[]>',
                         cell={'element': allocated[1], 'traces': []})
        if receiver and receiver.get('cell') is not None and method == 'get' and not actuals:
            return value('encoding_buffer_pointer', spelling=receiver['cell']['element'] + '*', cell=receiver['cell'])
        if spelling == 'std::string' and len(actuals) == 1 and actuals[0].get('cell', {}).get('element') == 'char':
            v = value('returned', 'std::string', traces=actuals[0]['cell']['traces'])
            return e.step(v, 'cstring_copied_to_string', info, node, conditions,
                          requires=['readable_null_terminated_output_buffer'])
        if not self.external(spelling, node, info): return None
        name = spelling.removeprefix('::'); argc, element = self.FUNCTIONS[name]
        if len(actuals) != argc: return None
        source, target, size = actuals[2], actuals[4], actuals[5]
        # A sizing call does not write or consume a buffer value.
        if size.get('literal') == '0': return value('scalar', 'int')
        cell = target.get('cell')
        if cell is None or cell['element'] != element:
            e.gap('encoding_output_buffer_unresolved', info, node, context, model=name)
            return None
        traces = source.get('cell', {}).get('traces', source.get('traces', []))
        requirement = {'kind': 'library_precondition', 'model': name, 'evidence': [e.evidence(info, node)],
                       'conditions': ['conversion_succeeds', 'input_length_and_output_capacity_valid',
                                      'source_encoding_matches_code_page', 'input_has_no_lossy_replacements']}
        v = e.step(value('encoded', traces=traces), 'win32_encoding_output', info, node, conditions + [requirement],
                   model=name, code_page=actuals[0].get('literal', text(node.child_by_field_name('arguments').named_children[0])),
                   input_length=text(node.child_by_field_name('arguments').named_children[3]), output_element=element)
        cell['traces'] = v['traces']
        return value('scalar', 'int')

    def invalidate(self, values, node, info, context):
        cells = {id(v['cell']): v['cell'] for v in values if 'cell' in v}
        for cell in cells.values():
            if cell['traces']:
                cell['traces'] = []
                self.engine.gap('unmodeled_encoding_buffer_effect', info, node, context)
