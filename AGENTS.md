# AGENTS.md

## プロジェクト概要
プラズモンカップリングシミュレーター（plasmon_coupling_simulator）。
Auナノ粒子集合体の光学スペクトル（Extinction/Scattering/Absorption）を、
CDA（結合双極子近似）とQCM（量子補正モデル）を組み合わせて計算する
ローカルWebアプリ。FastAPI + uvicorn + 静的Web UI（Plotly.js同梱）構成。

物理的な仮定・適用範囲・数値検証基準は、必ず以下を読んでから作業すること。
- docs/physics_assumptions.md（物理前提・適用範囲、最新版）
- docs/quantum_corrected_model_integration.md（QCM統合指示書）
- docs/validation_plan.md（検証計画・受け入れ基準）
- docs/references.md（採用文献一覧）
- docs/SPEC.md（Build Week MVPの確定仕様・D-1〜D-6）

実装の層分離と依存関係は `docs/repository_structure.md` を正とする。

これらのdocsとAGENTS.mdの記述が矛盾する場合は、docs側を正とし、
AGENTS.mdの記述を更新すること。

## セットアップ・実行コマンド
- 初回セットアップ: `setup_windows.bat`
  （.venv作成、依存パッケージインストール、Plotly.jsダウンロード＋ハッシュ検証）
- 起動: `run_app.bat`（http://127.0.0.1:8000 で自動起動）
- テスト: `.venv\Scripts\python -m pytest`
- 型・Lintチェック: `.venv\Scripts\python -m ruff check src tests`
  （ruffが未導入の場合は導入前に確認を取ること）

## コード変更時の必須ルール
1. 物理計算コア（src/physics/mie_reference.py,
   src/physics/polarizability.py, src/physics/green_tensor.py,
   src/physics/cda_solver.py, src/physics/qcm.py 等）を変更した場合、
   関連するpytestケース（tests/配下）を必ず実行し、
   全てパスすることを確認してから完了報告すること。
2. 新しい物理モデル・補正項を追加する場合、以下を厳守する。
   - 文献に基づかない数値・パラメータを独自に作らない。
   - 採用した文献名・出典・適用範囲をコード内コメントと
     docs/references.mdの両方に記録する。
    - 適用範囲外の入力（例: gap < 0.5 nm）は必ず明示的にエラーを返し、
      値を黒箱的に丸めたり無視したりしない。
    - QCMのAu距離依存値は、Esteban et al. (2012) Fig. 2dのAu実線から
      手順どおり抽出して版管理した暫定表だけを使う。Naの補足資料値の流用、
      Au係数の独自推定、表の有効範囲外への外挿は禁止する。
    - 暫定表を使う結果には、`provisional_digitized`、出典、図、対象曲線、
      校正点、読取誤差、補間法をJSONメタデータとUI注記に残す。
3. 依存パッケージを新規追加する場合は、requirements.txtへの追記前に
   必ずユーザーに確認を取ること。
4. README.mdの物理的制限、FastAPI/SSE/オフライン動作の記述は、
   `docs/SPEC.md` と物理前提文書に常に整合させる。物理的な適用範囲を
   変える変更は、先に該当docsを更新し、READMEだけで新しい数値基準を作らないこと。
5. 日本語コメントは必要最小限とし、変数名・関数名は英語（snake_case）
   で統一する。ユーザー向け説明文・コメントは、機械翻訳的な硬い表現を
   避け、簡潔で自然な日本語で書く。

## コーディング規約
- Python 3.11+、型ヒントを必須とする。
- 物理計算部分はSI単位系（m, kg, s, A）で統一し、
  nm単位との変換はio_utils.py等の境界層でのみ行う。
- pydanticまたはdataclassesで設定・入出力スキーマを管理する。
- 1関数1責務を基本とし、CDA/QCM/Mie参照計算のロジックを
  UI・APIハンドラのコードに混在させない。
- `src/physics/` はHTTP、SSE、HTML、ファイル入出力を知らない純粋な計算層とし、
  単位変換は `src/io/unit_conversion.py`、QCM表の読込は
  `src/io/qcm_parameter_table.py`、結果メタデータの型は `src/schemas/` に置く。

## テスト方針
- 新しい物理モデルを追加した場合、docs/validation_plan.mdに
  対応するTestケースを追記し、実装と同じPRで完結させる。
- 数値検証は相対誤差の許容範囲を明示し、`assert`のマジックナンバーには
  根拠コメントを付す。
- Test 1〜6はそれぞれ `test_mie_reference.py`、`test_cda_isolated_limit.py`、
  `test_dimer_coupling.py`、`test_qcm_safety.py`、
  `test_multiparticle_stability.py`、`test_io_reproducibility.py` に対応付ける。
- Test 5は3、5、10、20粒子に加え、`experimental/post-submission` の古典CDA限定拡張として
  50粒子（全粒子対のgapが5 nm超、QCMなし）を検証する。21〜50粒子はSSE計算経路に限定する。
- QCMの4層採用は、gap 0.5、0.7、0.9 nmでの3→4層の感度確認と4→5層の合否判定を
  満たした場合だけ許可する。暫定表の出典・有効範囲・読取誤差もTest 4で検証する。

## Git運用ルール
- 1つの意味のある変更（バグ修正・機能追加）が完了し、動作確認できたら、
  必ずその都度コミットすること。複数の変更をまとめて1コミットにしない。
- コミットメッセージは日本語で、変更内容が分かる短い要約にすること。
- 測定データ（*.txt, *.jws 等の研究データファイル）は
  .gitignore に追加し、コード変更のコミットに含めないこと。
- GitHub MCPを用いてPull Requestを作成した場合、マージは自動で行わず、
  必ずユーザーの明示的な承認を待つこと。

## 作業完了時の報告フォーマット
各タスク完了時、以下を必ず提示する。
1. 作成・変更したファイル一覧
2. 各ファイルの役割（1行程度）
3. 実行したテストコマンドと結果（pass/fail件数）
4. 今回の変更で新たに生じた物理的限界・注意点（あれば）
5. 次のPhase/タスクに進む前に確認すべき事項

## 禁止事項
- 存在しない実験値・文献値・検証済みでない数値の捏造。
- gap < 0.5 nmの入力を許容する変更（安全装置の無効化）。
- QCM適用要否の判定ロジックを、ユーザーの明示的な指示なく変更すること。
- 根拠資料・校正点・読取誤差を残さない暫定デジタイズ値を、文献値または検証済み値として扱うこと。
- テストを削除・スキップ設定にして「pass」を偽装すること。
