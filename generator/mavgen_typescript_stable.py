#!/usr/bin/env python3
"""
parse a MAVLink protocol XML file and generate a Node.js typescript module implementation

Based on original work Copyright Andrew Tridgell 2011
Released under GNU GPL version 3 or later
"""
import os
from . import mavtemplate

t = mavtemplate.MAVTemplate()


# Formats command labels into valid field names
def format_parameter(label):
    # Replace non-alphanumeric characters with underscores
    param_name = ''.join(c if c.isalnum() else '_' for c in label)
    
    # Ensures no keywords or leading digits
    return f"p_{param_name.lower()}"

# Convert snake_case to CamelCase
def snake_to_camel(str):
    parts = str.split("_")
    result = ""
    for part in parts:
        result += part.lower().capitalize()
    return result


def generate_enums(f, enums):
    print("Generating enums")

    for e in enums:
        if e.name == "MAV_CMD":
            generate_mav_cmds(f, e)
        else:
            f.write(f"/**\n * {e.description.strip()}\n */\n")
            f.write(f"export enum {snake_to_camel(e.name)} {{\n")
            for entry in e.entry:
                desc = entry.description.rstrip("\r").rstrip("\n").strip()
                if desc:
                    f.write(f"\t/** {desc} */\n")
                f.write(f"\t{entry.name} = {entry.value},\n")
            f.write("}\n\n")

        


def generate_mav_cmds(f, e):
    """Generate MAV_CMD enum and corresponding typed interfaces."""
    if e.name != "MAV_CMD":
        return

    # Enum with all command lookup
    f.write(f"/**\n * {e.description.strip()}\n */\n")
    f.write(f"export enum {snake_to_camel(e.name)} {{\n")
    for entry in e.entry:
        desc = entry.description.strip()
        if desc:
            f.write(f"\t/** {desc} */\n")
        f.write(f"\t{entry.name} = {entry.value},\n")
    f.write("}\n\n")

    # Base class for command types
    f.write("""
/** Base class for all MAVLink commands. */
export class BaseMavCmd {
    public param1: number = 0;
    public param2: number = 0;
    public param3: number = 0;
    public param4: number = 0;
    public param5: number = 0;
    public param6: number = 0;
    public param7: number = 0;

    constructor(params?: Partial<{ param1:number, param2:number, param3:number, param4:number, param5:number, param6:number, param7:number }>) {
        if (params) {
            Object.assign(this, params);
        }
    }
}\n\n""")
    

    # Class/constructor for each command type
    for entry in e.entry:
        f.write(f"/** {entry.description} */\n")
        f.write(f"export class {snake_to_camel(entry.name)} extends BaseMavCmd {{\n")

        parameters = []
        for p in entry.param:
            p = p.__dict__
            label = p['label'].strip()

            # Skip empty parameters
            if not label or label.lower() == "empty":
                continue            
            parameters.append((label, p['index'], p['description'].strip()))
        
        # Make constructor
        f.write("\tconstructor(")
        f.write(', '.join(f"{format_parameter(name)}: number" for name, _, _ in parameters))
        f.write(") {\n")
        
        f.write(f"\t\tsuper({{\n")
        for name, index, _ in parameters:
            f.write(f"\t\t\tparam{index}: {format_parameter(name)},\n")
        f.write(f"\t\t}});\n")
        f.write("\t}\n")

        f.write("}\n\n")


def generate_messages(f, msgs, xml):
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

        f.write(f"export class {snake_to_camel(m.name)} extends MAVLinkMessage {{\n")

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
                f.write(f"\tpublic {field.name}!: {snake_to_camel(field.enum)};\n")
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


def generate_message_registry(f, msgs):    
    f.write(
        "export const messageRegistry: Array<[number, new (system_id: number, component_id: number) => MAVLinkMessage]> = [\n"
    )
    msg_entries = []
    for m in msgs:
        msg_entries.append((m.id, snake_to_camel(m.name)))

    for m in sorted(msg_entries, key=lambda x: x[0]):
        f.write(f"\t[{m[0]}, {m[1]}],\n")
    
    f.write("];\n\n")


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
        generate_messages(f, msgs, xml[0])
        generate_message_registry(f, msgs)
