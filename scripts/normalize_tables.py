import csv
from io import StringIO
from typing import List, Dict, Any

def process_table_block(block: List[str], delimiter: str) -> List[str]:
    """
    Конвертирует блок строк с разделителями в Markdown-таблицу.
    """
    
    
    
    if len(block) < 2:
        return block
        
    
    
    
    f = StringIO('\n'.join(block))
    reader = csv.reader(f, delimiter=delimiter)
    
    md_block = []
    for i, row in enumerate(reader):
        
        cleaned_row = [col.strip() for col in row]
        md_line = "| " + " | ".join(cleaned_row) + " |"
        md_block.append(md_line)
        
        
        if i == 0:
            sep = "|" + "|".join(["---"] * len(cleaned_row)) + "|"
            md_block.append(sep)
            
    return md_block

def normalize_documents(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Проходит по документам и заменяет таблицы в форматах semicolon и tsv 
    на чистый Markdown.
    """
    for doc in documents:
        fmt = doc.get('content_format')
        
        
        if fmt not in ('semicolon', 'tsv'):
            continue
            
        delimiter = ';' if fmt == 'semicolon' else '\t'
        content = doc.get('content', '')
        lines = content.split('\n')
        
        normalized_lines = []
        table_block = []
        
        for line in lines:
            
            
            is_table_line = (
                delimiter in line 
                and not line.lstrip().startswith(('#', '- ', '* ', '> '))
            )
            
            if is_table_line:
                table_block.append(line)
            else:
                
                
                if table_block:
                    normalized_lines.extend(process_table_block(table_block, delimiter))
                    table_block = []
                normalized_lines.append(line)
        
        
        if table_block:
            normalized_lines.extend(process_table_block(table_block, delimiter))
            
        doc['content'] = '\n'.join(normalized_lines)
        
    return documents

if __name__ == "__main__":
    
    test_docs = [
        {
            "doc_id": "test-semicolon",
            "content_format": "semicolon",
            "content": (
                "Продукт Искра (P701); направление «Ежедневные расчёты».\n"
                "\n"
                "## Проверочный журнал\n"
                "\n"
                "Время UTC;event_key;revision;event_state;Результат\n"
                "06:11;P701-EV-001;1;PENDING;Не учитывать\n"
                "06:14;P701-EV-001;2;SETTLED;\"Точный повтор; пропустить\"\n"
                "\n"
                "Обычный текст с разделителем; но это не таблица."
            )
        },
        {
            "doc_id": "test-tsv",
            "content_format": "tsv",
            "content": (
                "День\tНачальный запас\tПриход\tУбытие\tКонечный запас\n"
                "2026-08-10\t1000\t200\t50\t1150\n"
                "2026-08-11\t1150\t0\t150\t1000"
            )
        }
    ]
    
    print("--- ДО НОРМАЛИЗАЦИИ (Документ 1) ---")
    print(test_docs[0]['content'])
    print("\n" + "="*50 + "\n")
    
    normalized_docs = normalize_documents(test_docs)
    
    print("--- ПОСЛЕ НОРМАЛИЗАЦИИ (Документ 1: Semicolon) ---")
    print(normalized_docs[0]['content'])
    print("\n" + "="*50 + "\n")
    print("--- ПОСЛЕ НОРМАЛИЗАЦИИ (Документ 2: TSV) ---")
    print(normalized_docs[1]['content'])