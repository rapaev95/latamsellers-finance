"""
LATAMSELLERS — File Unlocker
Tries known passwords to unlock protected Excel/PDF files.
"""
import io
import tempfile
from pathlib import Path


def unlock_excel(file_bytes: bytes, passwords: list[str]) -> tuple[bytes | None, str | None]:
    """
    Try to unlock a password-protected Excel file (.xlsx/.xls).
    Returns (unlocked_bytes, password_used) or (None, None) if all fail.
    """
    import msoffcrypto

    for pwd in passwords:
        try:
            file_in = io.BytesIO(file_bytes)
            file_out = io.BytesIO()

            of = msoffcrypto.OfficeFile(file_in)
            of.load_key(password=pwd)
            of.decrypt(file_out)

            file_out.seek(0)
            return file_out.read(), pwd
        except Exception:
            continue

    return None, None


def unlock_pdf(file_bytes: bytes, passwords: list[str]) -> tuple[bytes | None, str | None]:
    """
    Try to unlock a password-protected PDF file.
    Returns (unlocked_bytes, password_used) or (None, None) if all fail.
    """
    from PyPDF2 import PdfReader, PdfWriter

    for pwd in passwords:
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            if reader.is_encrypted:
                if not reader.decrypt(pwd):
                    continue
            else:
                # Not encrypted — return as-is
                return file_bytes, "(sem senha)"

            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)

            output = io.BytesIO()
            writer.write(output)
            output.seek(0)
            return output.read(), pwd
        except Exception:
            continue

    return None, None


def try_unlock(file_bytes: bytes, filename: str, passwords: list[str]) -> tuple[bytes | None, str | None, str]:
    """
    Auto-detect file type and try to unlock.
    Returns (unlocked_bytes, password_used, status_message).
    """
    ext = Path(filename).suffix.lower()

    if ext in (".xlsx", ".xls"):
        # First check if it's actually encrypted
        try:
            import msoffcrypto
            f = io.BytesIO(file_bytes)
            of = msoffcrypto.OfficeFile(f)
            if not of.is_encrypted():
                return file_bytes, None, "not_encrypted"
        except Exception:
            pass

        data, pwd = unlock_excel(file_bytes, passwords)
        if data:
            return data, pwd, "unlocked"
        return None, None, "failed"

    elif ext == ".pdf":
        from PyPDF2 import PdfReader
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            if not reader.is_encrypted:
                return file_bytes, None, "not_encrypted"
        except Exception:
            pass

        data, pwd = unlock_pdf(file_bytes, passwords)
        if data:
            return data, pwd, "unlocked"
        return None, None, "failed"

    else:
        return None, None, "unsupported"
