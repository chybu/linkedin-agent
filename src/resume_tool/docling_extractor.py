from pathlib import Path
from markitdown import MarkItDown

def extract_resume_as_markdown(input_path: str, output_path: str) -> None:
    md = MarkItDown()
    result = md.convert(input_path)
    Path(output_path).write_text(result.text_content, encoding="utf-8")


if __name__ == "__main__":
    extract_resume_as_markdown(
        "/Users/trungle/Downloads/Trung Le - Intern CV.pdf",
        "parsed_resume.md",
    )