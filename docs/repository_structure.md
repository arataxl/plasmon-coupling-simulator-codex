# リポジトリ構成・技術選定

## 位置付け

本書は `docs/SPEC.md` と `docs/quantum_corrected_model_integration.md` を
実装へ展開するための構成案である。以下のツリーは**実装時の目標構成**であり、
Phase 1では依存定義、`src/physics/material_data.py`、
`src/physics/mie_reference.py`、`src/schemas/simulation.py`、Test 1を作成した。
Phase 2では `src/physics/polarizability.py`、`src/physics/green_tensor.py`、
`src/physics/cda_solver.py`、Test 2・3を追加した。
物理的な適用範囲は既存の物理前提文書を正とする。

## 目標ディレクトリツリー

```text
.
├── AGENTS.md
├── README.md
├── setup_windows.bat                 # 初回セットアップ（実装Phaseで追加）
├── run_app.bat                       # localhost起動（実装Phaseで追加）
├── requirements.txt                  # Phase 1で承認済み依存を固定
├── requirements-dev.txt              # Phase 1でRuffを開発依存として分離
├── src/
│   ├── main.py                        # FastAPIアプリの生成、localhost用の組立て
│   ├── api/
│   │   ├── routers/
│   │   │   ├── simulations.py         # 計算開始・結果取得・キャンセルAPI
│   │   │   └── events.py              # SSE進捗イベントAPI
│   │   ├── dependencies.py            # API依存性、設定の受け渡し
│   │   └── error_handlers.py          # 入力・計算失敗のHTTP応答への変換
│   ├── services/
│   │   ├── simulation_service.py      # APIと計算コアをつなぐ計算オーケストレーション
│   │   └── job_manager.py             # 別プロセスの計算ジョブ、進捗、取消管理
│   ├── physics/
│   │   ├── material_data.py           # Au光学定数の補間と適用範囲検査
│   │   ├── mie_reference.py           # 単一球の完全Mie参照計算
│   │   ├── polarizability.py          # FCDA分極率、Kreibig切替
│   │   ├── green_tensor.py            # 遅延を含むdyadic Green tensor
│   │   ├── cda_solver.py              # 多粒子CDA複素線形方程式
│   │   └── qcm.py                     # QCM距離依存表の補間（薄層化・CDA統合は後続）
│   ├── io/
│   │   ├── unit_conversion.py         # UI/APIのnm等と内部SI単位の境界
│   │   ├── qcm_parameter_table.py     # 暫定デジタイズ表の読込・完全性検査
│   │   ├── importers.py               # 再計算用JSONの検証・読込
│   │   └── exporters.py               # CSV/JSONの生成（サーバー側の永続保存はしない）
│   └── schemas/
│       ├── simulation.py              # 入力条件・粒子・光源のPydanticスキーマ
│       ├── qcm.py                     # QCM表と出典情報のスキーマ
│       └── result.py                  # スペクトル、警告、JSONメタデータのスキーマ
├── web/
│   ├── index.html                     # 静的UIの入口
│   ├── css/app.css
│   ├── js/api_client.js                # REST/SSE接続
│   ├── js/input_form.js                # 入力、単位表示、クライアント側の初期検査
│   ├── js/progress.js                  # SSE進捗・キャンセル表示
│   ├── js/results.js                   # Plotly表示、警告、メタデータ表示
│   └── vendor/plotly.min.js            # ハッシュ検証済みの同梱資産
├── data/
│   ├── optical_constants/
│   │   ├── au_johnson_christy_1972.csv
│   │   └── metadata.yaml
│   └── qcm/
│       ├── gamma_g_au_digitized.csv   # Fig. 2dのAu実線を読取った暫定表
│       └── metadata.yaml              # 出典・単位・読取誤差・有効範囲
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── mie_reference_baseline.json
│   │   └── qcm_digitization_fixture.json
│   ├── test_mie_reference.py           # Validation Test 1
│   ├── test_cda_isolated_limit.py      # Validation Test 2
│   ├── test_dimer_coupling.py          # Validation Test 3
│   ├── test_qcm.py                     # Validation Test 4の基礎（表・補間）
│   ├── test_qcm_safety.py              # Validation Test 4
│   ├── test_multiparticle_stability.py # Validation Test 5
│   ├── test_io_reproducibility.py      # Validation Test 6
│   └── test_api_sse.py                 # localhost/SSE/取消の補助的な統合試験
└── docs/
    ├── SPEC.md
    ├── physics_assumptions.md
    ├── quantum_corrected_model_integration.md
    ├── validation_plan.md
    ├── references.md
    ├── project_reference.md
    └── repository_structure.md
```

Phase 1・2の物理コアに加え、`data/qcm/` とQCM距離依存表の補間、Test 4の基礎試験は
実装済みである。`web/`、API、QCM薄層とCDAの統合、Test 4の残り、Test 6は後続実装対象とする。
CSV/JSONはブラウザへのダウンロードとして返し、計算結果を
サーバー上の実行ディレクトリへ残さない。この方針により、取消時に部分データを
保存しないというMVP要件を満たしやすくする。

## 層の責務と依存方向

```text
web (静的UI)
  -> api (入力検証、SSE、HTTP応答)
  -> services (ジョブ管理、計算の編成)
  -> physics (Mie / 分極率 / Green tensor / CDA / QCM)
  <- io (材料・QCM表の読込、単位変換、CSV/JSON出力)
  <- schemas (全層で共有する検証済みデータ構造)
```

- `physics/` はHTTP、SSE、HTML、ファイルパスを知らない純粋な計算層とする。
- `api/` は物理モデルの適用可否を独自に決めない。`schemas/` と `services/` が返す
  検証済みのエラー・警告・メタデータをUI向けに変換するだけとする。
- `io/unit_conversion.py` を nm と SI 単位の唯一の境界とする。`physics/` 内は SI 単位で
  完結させる。
- `web/` は外部CDNを使わず、同一オリジンの静的資産だけを参照する。SSEは進捗・取消通知に
  限り、完了したスペクトルのみを `results.js` が描画する（D-1）。

## QCM暫定デジタイズ表の責務分離

`provisional_digitized` はUIだけの表示状態ではなく、計算入力から出力まで追跡可能な
データ上の状態とする。

| 場所 | 責務 | `provisional_digitized` の扱い |
| --- | --- | --- |
| `data/qcm/gamma_g_au_digitized.csv` と `data/qcm/metadata.yaml` | Fig. 2dのAu青色実線から抽出した22点と、出典・曲線・単位・読取誤差・有効範囲を版管理する。 | `parameter_status: provisional_digitized` と、校正点記録が未提供であることを保持する。数値を文献の係数表や検証済み値として扱わない。 |
| `src/schemas/qcm.py` | 表と出典情報を型付きで検証する。 | 必須フィールドが欠ける、または `qcm_parameter_status` が `provisional_digitized` 以外の場合は、MVPの暫定表として読込を拒否する。 |
| `src/io/qcm_parameter_table.py` | CSV表を読み、列・数値・単調性を検証する。 | 表を読み込むだけで、出典メタデータを再解釈・改変しない。範囲判定は物理層に委譲する。 |
| `src/physics/qcm.py` | 表から `log(gamma_g)` をPCHIP補間し、範囲外を安全に扱う。 | 下限未満はエラー、上限超過は外挿せず古典極限とする。4層QCM薄層とCDA統合は後続であり、Naの補足資料値や独自の指数関数を使わない。 |
| `src/schemas/result.py` | 計算結果の `qcm_applied` と `QcmMetadata` を保持する。 | `qcm_applied=true` の結果では、`qcm_parameter_status` と出典・校正点・読取誤差・補間法をJSON出力の必須項目にする。非適用時は適用しなかったことを明示し、暫定表の値を出力しない。 |
| `src/io/exporters.py` | CSV/JSONを出力する。 | CSVはスペクトル列、JSONは完全な `QcmMetadata` を保持する。取消・失敗時はどちらも出力しない。 |
| `src/api/` と `web/js/results.js` | API応答とUI注記を表示する。 | JSONの状態をそのまま伝え、0.5〜1 nm未満のQCM結果を「暫定デジタイズ値による参考値」と表示する。 |

QCM表の抽出手順、校正点、読取誤差の定義は
`docs/quantum_corrected_model_integration.md` を正とする。実装済みの表は利用者提供の
手動デジタイズ値であり、校正点が未提供という限界を取り除くものではない。

## 技術選定

| 領域 | 採用案 | 採用理由・条件 |
| --- | --- | --- |
| Web/API | FastAPI + uvicorn | SPECと既存Antigravity方針に合致する。`127.0.0.1`限定の静的配信、Pydanticスキーマ、SSEを一つのPythonプロセスで扱える。 |
| ジョブ進捗 | FastAPIのSSE + `multiprocessing` | 既存READMEの「API応答と重い計算を分離する」方針を維持する。D-1に従い、SSEは進捗・取消のみを配信する。 |
| Mie参照解 | `miepython` | 既存READMEに採用予定として記載があるため継続候補とする。完全Mie解を自作せず利用し、ライブラリ版・Auデータ・波長格子を固定してTest 1の基準配列を版管理する。アプリ本体と同一ライブラリのその場計算だけを比較基準にはしない。 |
| CDA / Green tensor | NumPy + SciPy | 複素配列、3N次元の線形方程式、数値状態の監視を明確に実装できる。MVPは最大20粒子（最大60自由度）であり、GPU・分散計算は不要である。 |
| 入出力・単位変換 | Python標準の `json` / `csv` + Pydantic | 仕様で必要なCSV/JSONとスキーマ検証に十分であり、pandasはMVPの必須依存にしない。既存READMEのpandas記載は、実際の依存定義がないため削除する。 |
| グラフ/UI | 同梱Plotly.js + HTML / CSS / Vanilla JavaScript | 既存の静的Web UI・オフライン方針を維持する。既存READMEのPlotly.js 2.24.1とSHA-256は、セットアップ実装時に同一値を検証する。 |
| テスト | pytest | `docs/validation_plan.md` のTest 1〜6をモジュール単位で対応付けられる。物理コアをAPI/UIより先に検証する。 |
| 静的解析 | Ruff（任意の開発依存） | 既存AGENTS.mdの方針を維持する。導入・依存定義は別途承認後に行う。 |

`requirements.txt` と `requirements-dev.txt` には、承認済みのバージョン範囲を記録した。
今後の依存追加または範囲変更には、FastAPI、uvicorn、NumPy、SciPy、miepython、pytest、
Ruffと同様にユーザー承認が必要である。

## Antigravity版からの変更点

- FastAPI + uvicorn、静的 `web/`、SSE、同梱Plotly.js、ローカル・オフライン動作は変更しない。
- 既存READMEでは物理計算モジュールが `src/` 直下に置かれる前提だった。実体が未作成であるため、
  API/UIとの混在を防ぐ `src/physics/`・`src/api/`・`src/io/`・`src/schemas/` へ明確に分離する。
- pandasは既存READMEにのみ予定依存として書かれ、仕様上必須ではない。標準ライブラリでCSV/JSONを
  扱うことで、Build Weekの依存追加・オフラインセットアップのリスクを減らす。
- QCMは従来の一般的な「適用済み」注記だけでなく、暫定デジタイズ表の出典と不確かさをJSONまで
  連鎖させる。これはD-2の再現性要件による追加である。
