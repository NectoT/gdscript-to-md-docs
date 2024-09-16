import os
from io import TextIOWrapper
import sys
import argparse
from pathlib import Path
import shutil
from dataclasses import dataclass, field, asdict
import re

import jinja2


def bbcode_to_md(text: str) -> str:
    text = re.sub(r'\[img.*\](.*)\[\/img\]', '![](' r'\1' + ')', text)

    text = re.sub(r'\[url=(.*)\](.*)\[\/url\]', '[' + r'\2' + ']' + '(' + r'\1' + ')', text)

    simple_tags = {
        'b': '**',
        'i': '_',
        's': '~~',
        'code': '`',
        'codeblock': '```',
        'br': '\n',
        'url': '',
    }

    for tag in simple_tags:
        text = text.replace(f'[{tag}]', simple_tags[tag])
        text = text.replace(f'[/{tag}]', simple_tags[tag])

    return text


@dataclass
class PropertyInfo:
    name: str
    type: str | None
    description: str | None
    default: str | None
    has_setter: bool = False
    has_getter: bool = False

    @staticmethod
    def _parse_inline_getset(info: 'PropertyInfo', text: str):
        # Separate functions syntax
        if len(re.findall(r'\s*set\s*=\s*(\w+)', text)) > 0:
            info.has_setter = True
        if len(re.findall(r'\s*get\s*=\s*(\w+)', text)) > 0:
            info.has_getter = True
        

    @staticmethod
    def parse_from_script(
        script: TextIOWrapper, 
        curr_line: str, 
        description: str | None, 
        onready: bool
    ) -> 'PropertyInfo':
        '''
        Parses property from the script file. curr_line is the last string read from the file
        with any annotation removed. Consumes all lines needed for full parsing
        ''' 

        name, type_hint, assign_op, default, setget_def = re.match(
            r'var\s+(\w+)(?:\s*\:\s*(?![gs]et\s*=)(\w+))?(?:\s*(\:?\s*\=)\s*(\w+))?\s*(?::(.+))?',
            curr_line
        ).groups()

        if onready:
            default = None

        if default is not None:
            if default[0] == '{':
                default = '{}' if default[0:default.find('}')].isspace() else '{...}'
            elif default[0] == '[':
                default = '[]' if default[0:default.find(']')].isspace() else '[...]'

        info = PropertyInfo(
            name=name,
            type= type_hint,
            description=description,
            default=default
        )

        if setget_def is not None:
            PropertyInfo._parse_inline_getset(info, setget_def)

        file_pos = script.tell()
        while line := script.readline():
            if not line[0].isspace():
                break
            
            PropertyInfo._parse_inline_getset(info, line)
            if line.lstrip().startswith('set'):
                info.has_setter = True
            elif line.lstrip().startswith('get'):
                info.has_getter = True
            
            file_pos = script.tell()

        
        script.seek(file_pos)
        return info


@dataclass
class ArgInfo:
    name: str
    type: str | None = None
    default: str | None = None

    @staticmethod
    def parse_definition(definition: str) -> list['ArgInfo']:
        '''
        Parses arguments from the function or signal definition string
        '''
        arg_str = definition[definition.find('(') + 1: definition.find(')')]
        arg_str.replace('\n', '')
        args: list[ArgInfo] = []
        for arg in arg_str.strip().split(','):
            default = None
            arg_type = None
            if '=' in arg:
                arg, default = map(lambda s: s.strip() ,arg.split('='))
            if ':' in arg:
                name, arg_type = map(lambda s: s.strip() ,arg.split(':'))
            else:
                name = arg
            args.append(ArgInfo(name=name, type=arg_type, default=default))
        
        return args



@dataclass
class MethodInfo:
    name: str
    description: str | None
    args: list[ArgInfo] = field(default_factory=list)
    return_type: str | None = None

    @staticmethod
    def parse_from_script(
        script: TextIOWrapper, 
        curr_line: str, 
        description: str | None
    ) -> 'SignalInfo':
        '''
        Parses method from the script file. curr_line is the last string read from the file
        with any annotation removed. Consumes all lines needed for full parsing
        '''

        args_lines = curr_line
        last_line = curr_line
        file_pos = script.tell()
        while line := script.readline():
            args_lines += line.strip()
            last_line = line
            if args_lines.rstrip().endswith(':'):
                break
            file_pos = script.tell()
        script.seek(file_pos)
        
        args = ArgInfo.parse_definition(args_lines)
        
        if '->' in last_line:
            return_type = last_line.rstrip()[last_line.find('->') + 2:-1].strip()
        else:
            return_type = None

        return MethodInfo(
            name=curr_line[curr_line.find(' '):curr_line.find('(')].strip(),
            args=args,
            return_type=return_type,
            description=description
        )


@dataclass
class SignalInfo:
    name: str
    description: str | None
    args: list[ArgInfo] = field(default_factory=list)

    @staticmethod
    def parse_from_script(
        script: TextIOWrapper, 
        curr_line: str, 
        description: str | None
    ) -> 'SignalInfo':
        '''
        Parses signal from the script file. curr_line is the last string read from the file
        with any annotation removed. Consumes all lines needed for full parsing
        '''

        args = []
        if '(' in curr_line:
            args_lines = curr_line
            file_pos = script.tell()
            while line := script.readline():
                if args_lines.rstrip().endswith(')'):
                    break
                args_lines += line.strip()
                file_pos = script.tell()
            script.seek(file_pos)
        
            args = ArgInfo.parse_definition(args_lines)

        return SignalInfo(
            name=curr_line[curr_line.find(' '):curr_line.find('(')].strip(),
            args=args,
            description=description
        )


@dataclass
class EnumInfo:
    name: str
    description: str | None
    vals: dict[str, str | None] = field(default_factory=dict)

    @staticmethod
    def parse_from_script(
        script: TextIOWrapper, 
        curr_line: str, 
        description: str | None
    ) -> 'EnumInfo':
        '''
        Parses enum from the script file. curr_line is the last string read from the file
        with any annotation removed. Consumes all lines needed for full parsing
        '''

        info = EnumInfo(
            name=curr_line.split()[1],
            description=description
        )

        if curr_line.rstrip()[-1] == '}':
            values = curr_line[curr_line.find('{') + 1:curr_line.find('}')].replace(' ', '').split(',')
            info.vals = dict.fromkeys([(val, None) for val in values])
            return info

        while line := script.readline():
            if line.isspace():
                continue
            
            if line.rstrip()[-1] == '}':
                return info
            if '##' in line:
                value, desc = line.split('##', maxsplit=1)
                info.vals[value.strip().replace(',', '')] = desc.strip()
            else:
                info.vals[line.strip().replace(',', '')] = None


@dataclass
class ClassInfo:
    file_path: Path
    name: str | None = None
    extends: str = ''
    summary: str | None = None
    description: str | None = None
    signals: list[SignalInfo] = field(default_factory=list)
    enums: list[EnumInfo] = field(default_factory=list)
    properties: list[PropertyInfo] = field(default_factory=list)
    methods: list[MethodInfo] = field(default_factory=list)

    def parse_script_header(script: TextIOWrapper, class_info: 'ClassInfo') -> None:
        '''
        Parses the first lines from the header to get the class name, its description and the
        base class. Consumes the parsed lines
        '''
        file_pos = script.tell()
        full_desc = ''
        def_found = False
        while line := script.readline():
            if def_found and not line.lstrip().startswith('##'):
                break

            if line.isspace():
                continue

            if line.startswith('class_name'):
                class_info.name = line.split()[1]
                line = line.split(maxsplit=2)[-1]
            
            if line.startswith('extends'):
                class_info.extends = line.split()[1]
                def_found = True
            
            if line.lstrip().startswith('##'):
                full_desc += line.lstrip()[2:].strip() + '\n'
            
            file_pos = script.tell()

        script.seek(file_pos)
        if full_desc == '':
            return
        
        if '' not in full_desc.splitlines():
            class_info.summary = full_desc.strip()
            return
        
        class_info.summary = '\n'.join(full_desc.splitlines()[:full_desc.splitlines().index('')])
        class_info.summary = bbcode_to_md(class_info.summary)
        class_info.description = '\n'.join(full_desc.splitlines()[full_desc.splitlines().index('') + 1:])
        class_info.description = bbcode_to_md(class_info.description)

    def parse_from_script(script_path: Path) -> 'ClassInfo':
        with script_path.open(encoding='utf-8') as script:
            class_info = ClassInfo(file_path=script_path)

            ClassInfo.parse_script_header(script, class_info)

            curr_docstring = ''
            while line := script.readline():
                if line.isspace():
                    continue

                if line.lstrip().startswith('##'):
                    curr_docstring += line[2::].lstrip()
                    continue

                annotation: str | None = None
                if line.startswith('@'):
                    if len(line.split()) == 1:
                        continue
                    annotation, line = line.split(maxsplit=1)

                description = bbcode_to_md(curr_docstring) if curr_docstring != '' else None
                if line.startswith('signal'):
                    class_info.signals.append(SignalInfo.parse_from_script(script, line, description))
                elif line.startswith('enum'):
                    class_info.enums.append(EnumInfo.parse_from_script(script, line, description))
                elif line.startswith('var'):
                    class_info.properties.append(
                        PropertyInfo.parse_from_script(
                            script, line, description, annotation == '@onready'
                        )
                    )
                elif line.startswith('func'):
                    class_info.methods.append(
                        MethodInfo.parse_from_script(script, line, description)
                    )

                curr_docstring = ''
        
        return class_info


if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser()
    arg_parser.description = (
        'Reads a Godot project directory and generates markdown documentation files for gd scripts'
    )
    arg_parser.add_argument(
        '-p', '--project', 
        help='Path to Godot project with gdscript files',
        default=os.getcwd(),
    )
    arg_parser.add_argument(
        '-o', '--output', 
        help='Directory to save generated markdown files to',
        default=os.getcwd() + '/gd_docs/'
    )
    arg_parser.add_argument(
        '-t', '--template', 
        help='Jinja2 template file to use for generating markdown files',
        default=Path(sys.argv[0]).parent.joinpath('class_doc_template.md'),
    )
    arg_parser.add_argument(
        '-s', '--script-templates',
        help=(
            'Path to script templates directory relative to project directory. '
            'Default value is "script_templates"'
        ),
        default=Path('script_templates')
    )
    arg_parser.add_argument(
        '-n', '--named-only',
        help='Restricts parsing to only named classes',
        action='store_true'
    )
    arg_parser.add_argument(
        '-i', '--ignore-warnings',
        help='Ignore any situations that require additional confirmation from user',
        action='store_true'
    )

    args = arg_parser.parse_args()
    project_dir: Path = Path(args.project)

    output_dir: Path = Path(args.output)

    if os.path.isdir(args.output) and any(os.scandir(args.output)):
        if not args.ignore_warnings:
            print('Output directory is non-empty. If you continue, all of it\'s contents will be deleted.')
            print('Do you want to continue? y/n')
            answer = input()
            if answer != 'y':
                print('Exiting')
                exit()

        shutil.rmtree(args.output)
    
    jinja_env = jinja2.Environment(trim_blocks=True, lstrip_blocks=True)
    with Path(args.template).open(encoding='utf-8') as md_template_file:
        md_template = jinja_env.from_string(md_template_file.read())

    class_infos: dict[str, ClassInfo] = {}
    addons_dir = project_dir.joinpath('addons')
    script_templates_dir = project_dir.joinpath(args.script_templates)
    for script_path in project_dir.rglob('*.gd'):
        if addons_dir in script_path.parents or script_templates_dir in script_path.parents:
            continue

        class_info: ClassInfo = ClassInfo.parse_from_script(script_path.relative_to(project_dir))
        if class_info.name is not None:
            class_infos[class_info.name] = class_info
        elif not args.named_only:
            path_based_name = '-'.join(script_path.relative_to(project_dir).parts)
            class_infos[path_based_name] = class_info

    for class_name in class_infos:
            class_info = class_infos[class_name]

            class_path = Path('')
            base_class = class_info.extends
            while True:
                if base_class.replace('"', '').replace("'", '').endswith('.gd'):
                    base_class = base_class.replace('"', '').replace("'", '')
                    base_class = base_class.removeprefix('res://').replace('/', '-')

                class_path = Path(base_class).joinpath(class_path)
                
                if base_class not in class_infos:
                    break
                
                base_class = class_infos[base_class].extends
            
            md_file_path = output_dir.joinpath(class_path).joinpath(class_name + '.md')
            md_file_path.parent.mkdir(parents=True, exist_ok=True)
            with md_file_path.open(mode='w', encoding='utf-8') as md_file:
                md_file.write(md_template.render(asdict(class_info)))