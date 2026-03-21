## AiPack
폴더와 내부 파일들을 single binary data로 (계층유지) -> ai가 읽기 쉽게

<details>
<summary><strong>📦 v1</strong></summary>

### index 기반

- 중앙 index(JSON) → 전체 파일 메타데이터 포함
- offset 기반 랜덤 접근
### compression
- zstd 압축
- 근데 압축하면 ai가 못 읽음
### checksum
- SHA-256 checksum
- 원본 기준 검증 (압축 여부와 무관)
### mmap 기반 reader
- zero-copy 접근
### manifest
- 이거 있어야 ai가 단일파일로 인식 x 패킹 파일로 인식 o
- 이거 때매 용량 몇 바이트 늘어나긴 함


### cli.py
```cpp
// ### 폴더 패킹 ###
python cli.py pack /* 패킹할 폴더 경로 */ /* 결과물 경로 및 파일명.aip */
//--compression none <-- 압축 없음
//--compression zlib <-- zlib 압축
//--compression zstd <-- Zstandard 압축

// ### 파일 목록 manifest 기반 출력 ###
python cli.py ls /* aip 파일 */

// ### 파일 정보 ###
python cli.py info /* aip 파일 */

// ### 폴더 구조 보기 ###
python cli.py tree /* aip 파일 */

// ### 파일 내용 보기 ###
python cli.py cat /* aip 파일 */ /* 목표 파일의 경로 및 파일명 */

// ### aip 파일 언패킹 ###
python cli.py extract /* aip 파일 */ /* 언패킹 위치 폴더 */

// ### aip 파일 내부 단일파일 언패킹 ###
python cli.py extract-one /* aip 파일 */ /* aip 파일 내부 단일파일 */ /* 언패킹 위치 폴더 */

// ### 파일 무결성 검증 (checksum) ###
python cli.py verify /* aip 파일 */

// ### manifest JSON 출력 ###
python cli.py manifest /* aip 파일 */
```

### 메모

- streaming

대용량 파일 chunk 읽기

partial decode

- 병렬 처리

extract 병렬화

dataset prefetch

- index 포맷 변경

JSON → msgpack / binary

ultra-large archive 대응

- remote dataset

HTTP range 요청

cloud dataset 직접 사용

- PyTorch / ML 통합

```py
class TorchDataset(AIPKDataset):
```

바로 학습 데이터로 사용 가능

- incremental pack

- append mode

- diff archive

- reader mmap + fallback 더 안정화

- verify 옵션 CLI에서도 제공

- progress bar thread-safe

- error 메시지 표준화
</details>
