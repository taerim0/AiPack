## AiPack
폴더와 내부 파일들을 single binary data로 (계층유지) -> ai가 읽기 쉽게

<details>
<summary><strong>📦 v1</strong></summary>


index 기반

- 중앙 index(JSON) → 전체 파일 메타데이터 포함
- offset 기반 랜덤 접근

compression

- zstd 압축
- 근데 압축하면 ai가 못 읽음

checksum

- SHA-256 checksum
- 원본 기준 검증 (압축 여부와 무관)

mmap 기반 reader

- zero-copy 접근

manifest

- 이거 있어야 ai가 단일파일로 인식 x 패킹 파일로 인식 o
- 이거 때매 용량 몇 바이트 늘어나긴 함


cli.py

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

메모

- streaming

- - 대용량 파일 chunk 읽기

- - partial decode

- 병렬 처리

- - extract 병렬화

- - dataset prefetch

- index 포맷 변경

- - JSON → msgpack / binary

- - ultra-large archive 대응

- remote dataset

- - HTTP range 요청

- - cloud dataset 직접 사용

- PyTorch / ML 통합

```py
class TorchDataset(AIPKDataset):
```

- - 바로 학습 데이터로 사용 가능

- incremental pack

- append mode

- diff archive

- reader mmap + fallback 더 안정화

- verify 옵션 CLI에서도 제공

- progress bar thread-safe

- error 메시지 표준화

</details>

## v1


핵심기능이 뭔가 이상함.. 폴더 패킹하면 ai가 파일들 읽긴 읽는데 완벽하게 읽진 않음

내부에 텍스트기반의 ai 전용 가이드라인 같은게 있어야 한 번에 완벽하게 읽을 거 같은데

폴더를 단일 파일화해서 ai가 읽기 쉽게 만든다는 기존의 목적을 먼저 달성하고 여러 기능 추가해야하는데 그냥 신나서 제대로 되는지 체크도 잘 안 한듯


폴더를 다 패킹해서 한 폴더의 모든 데이터를 한번에 ai한테 읽도록 시키겠다는 기존의 목표보다는

계층적 관계를 가진 여러 파일들을 프로그램 내부에서 선택하고, 해당 파일들의 계층적 관계와 내부 데이터들을 텍스트화하여 하나의 파일로 만드는게 더 실용적일거 같음

내부 저장공간에서 파일 몇개를 선택하도록 ux/ui를 제공하고, 선택된 파일들 중 가장 최상위폴더를 바탕으로한 계층구조와, 파일의 내용들을 텍스터화해서 담고있는 파일을 만들게 하는 프로그램