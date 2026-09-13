import os
import re
import ast
from typing import Iterator, Dict, Any



SQL_STRING = r"'(?:[^'\\]|\\.|'')*'"

SQL_ARRAY = r"\[(?:[^'\]]|" + SQL_STRING + r")*\]"

SQL_OTHER = r"[^,]+"


VALUE_PATTERN = re.compile(f"({SQL_STRING})|({SQL_ARRAY})|({SQL_OTHER})")


def parse_sql_row(row_str: str) -> list:
    """Извлекает отдельные значения из строки-кортежа SQL."""
    if row_str.startswith('('): row_str = row_str[1:]
    if row_str.endswith(')'): row_str = row_str[:-1]
    
    values = []
    for match in VALUE_PATTERN.finditer(row_str):
        s_val, arr_val, other_val = match.groups()
        
        if s_val is not None:
            
            inner = s_val[1:-1]
            inner = inner.replace("''", "'").replace("\\'", "'")
            inner = inner.replace("\\n", "\n").replace("\\t", "\t").replace("\\\\", "\\")
            values.append(inner)
            
        elif arr_val is not None:
            
            try:
                values.append(ast.literal_eval(arr_val.replace('NULL', 'None')))
            except Exception:
                values.append(arr_val)
                
        elif other_val is not None:
            val = other_val.strip()
            if not val:
                continue
            
            if val.upper() == 'NULL':
                values.append(None)
            elif val.isdigit() or (val.startswith('-') and val[1:].isdigit()):
                values.append(int(val))
            else:
                try:
                    values.append(float(val))
                except ValueError:
                    values.append(val)
                    
    return values


def parse_sql_dump(file_path: str) -> Iterator[Dict[str, Any]]:
    """Построчно читает SQL-дамп и отдает записи в виде словарей."""
    columns = []
    in_insert = False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('INSERT INTO'):
                col_match = re.search(r'\((.*?)\)', line)
                if col_match:
                    columns = [c.strip().strip('`"') for c in col_match.group(1).split(',')]
                in_insert = True
                continue
                
            if in_insert:
                if line.startswith('('):
                    if line.endswith('),'):
                        row_str = line[:-1]
                    elif line.endswith(');'):
                        row_str = line[:-1]
                        in_insert = False
                    else:
                        row_str = line
                        
                    try:
                        row_values = parse_sql_row(row_str)
                        if len(columns) == len(row_values):
                            yield dict(zip(columns, row_values))
                        else:
                            
                            pass
                    except Exception as e:
                        print(f"Ошибка парсинга строки: {e}")
                        
                elif line.endswith(';'):
                    in_insert = False


if __name__ == "__main__":
    import os

    
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sql_file = os.path.normpath(
        os.path.join(script_dir, "..", "meridian_hackathon_knowledge_base", "meridian_hackathon_knowledge_base", "ai_copilot_documents.sql")
    )
    
    if not os.path.exists(sql_file):
        print(f"Файл не найден по пути: {sql_file}")
    else:
        print(f"Начинаю парсинг {sql_file}...\n")
        
        documents_generator = parse_sql_dump(sql_file)
        
        
        for i, record in enumerate(documents_generator):
            if i >= 2:
                break
                
            print(f"--- Запись {i + 1} ---")
            for key, value in record.items():
                val_str = str(value)
                if len(val_str) > 100:
                    val_str = val_str[:97] + "..."
                print(f"{key}: {val_str}")
            print("\n")
        
        print("Парсинг успешно запущен и работает без синтаксических ошибок.")