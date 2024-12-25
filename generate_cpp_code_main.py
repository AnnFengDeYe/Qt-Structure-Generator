#!/usr/bin/env python3
# generate_cpp_code.py

import json
import sys

# 模板定义
HEADER_TEMPLATE = '''#ifndef {header_guard}
#define {header_guard}

#include <QtCore>
#include <QVector>
#include <QDataStream>

#pragma pack(push, 1)

{struct_definitions}

#pragma pack(pop)

{serialization_functions}

#endif // {header_guard}
'''

STRUCT_TEMPLATE = '''
// {struct_comment}
struct {struct_name} {{
{member_definitions}

    // 默认构造函数
    {struct_name}()
{constructor_initialization}
    {{}}
{allocate_functions}
}};
'''

SERIALIZATION_TEMPLATE = '''
// 序列化与反序列化 {struct_name}
inline QDataStream& operator<<(QDataStream& stream, const {struct_name}& obj) {{
{serialize_code}
    return stream;
}}

inline QDataStream& operator>>(QDataStream& stream, {struct_name}& obj) {{
{deserialize_code}
    return stream;
}}
'''

def generate_cpp_code(data):
    structs = data['structs']

    # 收集所有结构体的序列化代码
    struct_definitions = ''
    serialization_functions = ''

    struct_dict = {struct['name']: struct for struct in structs}

    # 基本数据类型列表
    basic_types = ['quint8', 'quint16', 'quint32', 'quint64',
                   'qint8', 'qint16', 'qint32', 'qint64',
                   'float', 'double']

    for struct in structs:
        struct_name = struct['name']
        members = struct['members']
        struct_comment = struct.get('comment', '')

        # 生成成员变量声明
        member_definitions = ''
        constructor_initialization = ''
        allocate_functions = ''
        serialize_code = ''
        deserialize_code = ''

        # 用于记录需要生成 allocateList 函数的 QVector 成员
        QVector_members = []

        for idx, member in enumerate(members):
            member_type = member['type']
            member_name = member['name']
            array_size = member.get('arraySize', None)
            comment = member.get('comment', '')

            # 成员变量声明
            if array_size:
                member_line = f'    {member_type} {member_name}[{array_size}];'
            else:
                member_line = f'    {member_type} {member_name};'

            if comment:
                member_line += f'  /**< {comment} */\n'
            else:
                member_line += '\n'

            member_definitions += member_line

            # 默认构造函数初始化
            if array_size:
                # 数组类型，使用 memset 初始化
                init_line = f'memset({member_name}, 0, sizeof({member_name}));'
            elif member_type.startswith('QVector'):
                init_line = ''
            elif member_type in basic_types:
                init_line = f'{member_name}(0)'
            elif member_type in struct_dict:
                init_line = ''
            else:
                init_line = f'{member_name}(0)'

            if init_line:
                if not constructor_initialization:
                    constructor_initialization = ':\n        ' + init_line
                else:
                    constructor_initialization += ',\n        ' + init_line

            # 序列化与反序列化代码
            if array_size:
                # 数组类型
                if member_type == 'char':
                    # char数组，使用 writeRawData 和 readRawData，使用 sizeof()
                    serialize_code += f'    stream.writeRawData(obj.{member_name}, sizeof(obj.{member_name}));\n'
                    deserialize_code += f'    stream.readRawData(obj.{member_name}, sizeof(obj.{member_name}));\n'
                elif member_type in basic_types:
                    # 基本数据类型数组，使用循环，使用 sizeof()
                    array_length = f'static_cast<int>(sizeof(obj.{member_name}) / sizeof(obj.{member_name}[0]))'
                    serialize_code += f'    // 序列化数组 {member_name}\n'
                    serialize_code += f'    for (int i = 0; i < {array_length}; ++i) {{\n'
                    serialize_code += f'        stream << obj.{member_name}[i];\n'
                    serialize_code += f'    }}\n'
                    deserialize_code += f'    // 反序列化数组 {member_name}\n'
                    deserialize_code += f'    for (int i = 0; i < {array_length}; ++i) {{\n'
                    deserialize_code += f'        stream >> obj.{member_name}[i];\n'
                    deserialize_code += f'    }}\n'
                else:
                    # 其他类型的数组，可以根据需要扩展
                    pass
            elif member_type.startswith('QVector'):
                # QVector 类型
                element_type = member_type[member_type.find('<')+1 : member_type.find('>')]

                # 查找前一个成员变量是否为计数变量
                if idx > 0:
                    prev_member = members[idx - 1]
                    count_member_name = prev_member['name']
                    count_member_type = prev_member['type']
                    if count_member_type in basic_types:
                        # 记录需要生成 allocateList 函数
                        QVector_members.append((member_name, count_member_name))
                        # 序列化
                        serialize_code += f'    // 序列化 {member_name}\n'
                        # 不序列化大小，直接序列化元素
                        serialize_code += f'    for (const auto& item : obj.{member_name}) {{\n'
                        serialize_code += f'        stream << item;\n'
                        serialize_code += f'    }}\n'
                        # 反序列化
                        deserialize_code += f'    // 反序列化 {member_name}\n'
                        deserialize_code += f'    obj.allocate{member_name[1:]}();\n'
                        # 使用基于索引的循环
                        deserialize_code += f'    for (int i = 0; i < obj.{member_name}.size(); ++i) {{\n'
                        deserialize_code += f'        stream >> obj.{member_name}[i];\n'
                        deserialize_code += f'    }}\n'
                    else:
                        # 前一个成员不是计数变量，按照原来的方式处理
                        serialize_code += f'    // 序列化 {member_name} 的大小\n'
                        serialize_code += f'    stream << obj.{member_name}.size();\n'
                        serialize_code += f'    // 序列化 {member_name} 的元素\n'
                        serialize_code += f'    for (const auto& item : obj.{member_name}) {{\n'
                        serialize_code += f'        stream << item;\n'
                        serialize_code += f'    }}\n'
                        deserialize_code += f'    // 反序列化 {member_name} 的大小\n'
                        deserialize_code += f'    int {member_name}_size = 0;\n'
                        deserialize_code += f'    stream >> {member_name}_size;\n'
                        deserialize_code += f'    obj.{member_name}.resize({member_name}_size);\n'
                        deserialize_code += f'    // 反序列化 {member_name} 的元素\n'
                        deserialize_code += f'    for (int i = 0; i < {member_name}_size; ++i) {{\n'
                        deserialize_code += f'        stream >> obj.{member_name}[i];\n'
                        deserialize_code += f'    }}\n'
                else:
                    # 没有前一个成员，按照原来的方式处理
                    serialize_code += f'    // 序列化 {member_name} 的大小\n'
                    serialize_code += f'    stream << obj.{member_name}.size();\n'
                    serialize_code += f'    // 序列化 {member_name} 的元素\n'
                    serialize_code += f'    for (const auto& item : obj.{member_name}) {{\n'
                    serialize_code += f'        stream << item;\n'
                    serialize_code += f'    }}\n'
                    deserialize_code += f'    // 反序列化 {member_name} 的大小\n'
                    deserialize_code += f'    int {member_name}_size = 0;\n'
                    deserialize_code += f'    stream >> {member_name}_size;\n'
                    deserialize_code += f'    obj.{member_name}.resize({member_name}_size);\n'
                    deserialize_code += f'    // 反序列化 {member_name} 的元素\n'
                    deserialize_code += f'    for (int i = 0; i < {member_name}_size; ++i) {{\n'
                    deserialize_code += f'        stream >> obj.{member_name}[i];\n'
                    deserialize_code += f'    }}\n'
            elif member_type in struct_dict:
                # 自定义结构体类型
                serialize_code += f'    stream << obj.{member_name};\n'
                deserialize_code += f'    stream >> obj.{member_name};\n'
            else:
                # 基本类型
                serialize_code += f'    stream << obj.{member_name};\n'
                deserialize_code += f'    stream >> obj.{member_name};\n'

        # 生成 allocateList 函数
        for QVector_member_name, count_member_name in QVector_members:
            func_name = f'allocate{QVector_member_name[1:]}'
            allocate_function = f'''
    // 根据 {count_member_name} 分配 {QVector_member_name} 大小
    void {func_name}() {{
        {QVector_member_name}.resize({count_member_name});
    }}'''
            allocate_functions += allocate_function

        # 生成结构体定义
        struct_definition = STRUCT_TEMPLATE.format(
            struct_comment=f'/**< {struct_comment} */' if struct_comment else '',
            struct_name=struct_name,
            member_definitions=member_definitions.rstrip(),
            constructor_initialization=constructor_initialization,
            allocate_functions=allocate_functions
        )

        struct_definitions += struct_definition

        # 生成序列化与反序列化函数
        serialization_function = SERIALIZATION_TEMPLATE.format(
            struct_name=struct_name,
            serialize_code=serialize_code.rstrip(),
            deserialize_code=deserialize_code.rstrip()
        )

        serialization_functions += serialization_function

    # 生成最终的头文件内容
    header_guard = 'GENERATED_STRUCTS_H'
    final_code = HEADER_TEMPLATE.format(
        header_guard=header_guard,
        struct_definitions=struct_definitions.strip(),
        serialization_functions=serialization_functions.strip()
    )

    return final_code

def main():
    # 从标准输入读取 JSON 数据
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"JSON 解码错误: {e}", file=sys.stderr)
        sys.exit(1)

    # 生成 C++ 代码
    cpp_code = generate_cpp_code(data)

    # 输出到标准输出
    print(cpp_code)

if __name__ == "__main__":
    main()