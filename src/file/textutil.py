def read_text(file_path: str) -> str | None:
    """파일을 UTF-8 텍스트로 안전하게 읽는다.

    바이너리 파일, 인코딩 문제, 접근 불가(디렉터리/권한 등) 시 예외를 던지는 대신
    None을 돌려준다. 게임 애셋(이미지, 사운드 등)처럼 텍스트가 아닌 파일이 섞인
    프로젝트에서도 파이프라인이 죽지 않도록 하는 공용 진입점.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except (UnicodeDecodeError, OSError):
        return None
