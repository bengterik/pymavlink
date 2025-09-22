#!/usr/bin/env python3
"""
parse a MAVLink protocol XML file and generate a Node.js typescript module implementation

Based on original work Copyright Andrew Tridgell 2011
Released under GNU GPL version 3 or later
"""
import os
from . import mavtemplate

t = mavtemplate.MAVTemplate()


def camelcase(str):
    parts = str.split("_")
    result = ""
    for part in parts:
        result += part.lower().capitalize()
    return result


def generate_enums(f, enums):
    print("Generating enums")

    for e in enums:
        if e.name == "MAV_CMD":
            # Generate MAV_CMD enum and interfaces specially
            generate_mav_cmd_interfaces(f, e)
        else:
            f.write(f"/**\n * {e.description.strip()}\n */\n")
            f.write(f"export enum {camelcase(e.name)} {{\n")
            for entry in e.entry:
                desc = entry.description.rstrip("\r").rstrip("\n").strip()
                if desc:
                    f.write(f"\t/** {desc} */\n")
                f.write(f"\t{entry.name} = {entry.value},\n")
            f.write("}\n\n")

        


def generate_mav_cmd_interfaces(f, e):
    """Generate MAV_CMD enum and corresponding typed interfaces."""
    if e.name != "MAV_CMD":
        return

    # Enum first
    f.write(f"/**\n * {e.description.strip()}\n */\n")
    f.write(f"export enum {camelcase(e.name)} {{\n")
    for entry in e.entry:
        desc = entry.description.strip()
        if desc:
            f.write(f"\t/** {desc} */\n")
        f.write(f"\t{entry.name} = {entry.value},\n")
    f.write("}\n\n")

    # Interfaces for each command entry
    for entry in e.entry:
        if not hasattr(entry, "param") or not entry.param:
            continue

        # Raw paramN interface
        f.write(f"/** Raw MAVLink parameters for {entry.name} */\n")
        f.write(f"export interface {camelcase(entry.name)}Raw {{\n")
        for p in entry.param:
            p = p.__dict__
            f.write(f"\t/** {p['description'].strip()} */\n")
            f.write(f"\tparam{p['index']}: number;\n")
        f.write("}\n\n")

        # Friendly interface
        f.write(f"/** Friendly parameters for {entry.name} */\n")
        f.write(f"export interface {camelcase(entry.name)} {{\n")
        for p in entry.param:
            p = p.__dict__
            label = p['label'].strip().lower()
            if not label or label.lower() == "empty":
                continue
            # TS-safe name: remove non-alphanumeric, start with lowercase
            if not label or label.lower() == "empty":
                continue
            # Remove non-alphanumeric
            prop_name = ''.join(c if c.isalnum() else '_' for c in label)
            # Prefix with 'num' if it starts with a digit
            if prop_name[0].isdigit():
                prop_name = f"num{prop_name}"
            # lowercase first character
            prop_name = prop_name[0].lower() + prop_name[1:]
            f.write(f"\t/** {p['description'].strip()} */\n")
            f.write(f"\t{prop_name}: number;\n")
        f.write("}\n\n")


def generate_classes(f, msgs, xml):
    print("Generating class definitions")

    ts_types = {
        "uint8_t": "number",
        "uint16_t": "number",
        "uint32_t": "number",
        "uint64_t": "number",
        "int8_t": "number",
        "int16_t": "number",
        "int32_t": "number",
        "int64_t": "number",
        "float": "number",
        "double": "number",
        "char": "string",
    }
    
    f.write("""
        export abstract class MAVLinkMessage {
            public _message_id!: number;
            public _message_name!: string;
            public _crc_extra!: number;
            public _message_fields!: [string, string, boolean][];
            
            constructor(public system_id: number, public component_id: number) {}
        }""")

    # Write all classes
    for m in msgs:
        if xml.wire_protocol_version == "1.0":
            raise Exception("WireProtocolException", "Please use WireProtocol = 2.0 only.")

        # Class-level JSDoc
        class_desc = m.description.strip()
        if class_desc:
            f.write("/**\n")
            for line in class_desc.splitlines():
                f.write(f" * {line.strip()}\n")
            f.write(" */\n")

        f.write(f"export class {camelcase(m.name)} extends MAVLinkMessage {{\n")

        # Fields
        for field in m.fields:
            desc = field.description.strip()
            if len(desc.splitlines()) == 1 and len(desc) < 80:
                f.write(f"\t/** {desc} */\n")
            else:
                f.write("\t/**\n")
                for line in desc.splitlines():
                    f.write(f"\t * {line.strip()}\n")
                f.write("\t */\n")

            if field.enum:
                f.write(f"\tpublic {field.name}!: {camelcase(field.enum)};\n")
            else:
                f.write(f"\tpublic {field.name}!: {ts_types[field.type]};\n")
            f.write("\n")

        # Metadata
        f.write(f"\tpublic _message_id: number = {m.id};\n")
        f.write(f"\tpublic _message_name: string = '{m.name}';\n")
        f.write(f"\tpublic _crc_extra: number = {m.crc_extra};\n")

        # Field definitions for MAVLink
        f.write("\tpublic _message_fields: [string, string, boolean][] = [\n")
        for i, fieldname in enumerate(m.ordered_fieldnames):
            field = next(field for field in m.fields if field.name == fieldname)
            extension = "true" if m.extensions_start is not None and i >= m.extensions_start else "false"
            f.write(f"\t\t['{field.name}', '{field.type}', {extension}],\n")
        f.write("\t];\n")

        f.write("}\n\n")

    # f.write(f"import {{ {', '.join([camelcase(m.name) for m in msgs])} }} from './messages';\n\n")
    f.write(
        "export const messageRegistry: Array<[number, new (system_id: number, component_id: number) => MAVLinkMessage]> = [\n"
    )
    for m in msgs:
        f.write(f"\t[{m.id}, {camelcase(m.name)}],\n")
    f.write("];\n")


def generate_tsconfig(basename):
    with open("{}/tsconfig.json".format(basename), "w") as f:
        f.write(
            '{\n  "compilerOptions": {\n    "target": "es5",\n    "module": "commonjs",'
            '\n    "declaration": true,\n    "declarationMap": true,\n    "sourceMap": true,'
            '\n    "outDir": "./",\n    "strict": true,\n    "esModuleInterop": true\n  },'
            '\n  "include": [\n    "./"\n  ],\n  "exclude": [\n    "**/*.d.ts",'
            '\n    "**/*.d.ts.map",\n    "**/*.js",\n    "**/*.js.map"\n  ]\n}'
        )


def generate_commands(f, commands):
    print("Generating commands")

    f.write("/**\n * MAVLink Commands\n */\n")
    f.write("export enum MAV_CMD {\n")
    for cmd in commands:
        desc = cmd.description.strip()
        if desc:
            f.write(f"\t/** {desc} */\n")
        f.write(f"\t{cmd.name} = {cmd.value},\n")
    f.write("}\n\n")
    
def generate(base_dir, xml):
    output_file = os.path.join(base_dir, "mavlink.ts")
    msgs = []
    enums = []
    filelist = []

    for x in xml:
        msgs.extend(x.message)
        enums.extend(x.enum)
        filelist.append(os.path.basename(x.filename))

    with open(output_file, "w") as f:
        generate_enums(f, enums)
        generate_classes(f, msgs, xml[0])
    # generate_tsconfig(basename)
