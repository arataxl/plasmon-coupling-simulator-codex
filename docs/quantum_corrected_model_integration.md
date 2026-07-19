# QCM統合指示書

## 目的
粒子間表面ギャップが1 nm未満の領域において、電子トンネル効果を
無視した古典的CDA/Green tensorモデルが示す非物理的な発散
（電場増強の無限大化、消光断面積の異常な増大）を抑制するため、
Quantum Corrected Model（QCM）を計算コアに統合する。

## 採用する理論的根拠
本実装は、以下の文献で提案されたQCMをそのまま採用する。
独自の数値・パラメータを新規に導出・捏造しない。

- Esteban, R.; Borisov, A. G.; Nordlander, P.; Aizpurua, J.
  "Bridging quantum and classical plasmonics with a
  quantum-corrected model."
  Nature Communications 3, 825 (2012).
  DOI: 10.1038/ncomms1806

原論文本文の「Quantum plasmonics in large metallic systems」節は、半径25 nmの
Au球を `epsilon_inf = 1`、`hbar * omega_p = 7.9 eV`、
`hbar * gamma_p = 0.09 eV` のDrudeモデルで記述する。この記述はAu jellium・
大波長域向けで、2.0 eV以上で重要となる帯間遷移を含まない。これらは原論文の
QCM例における材料設定として記録するものであり、Johnson and Christy (1972) の
バルク `n + ik` を基にするFCDA/Kreibig補正のパラメータとして転用しない。
本タスクでは距離依存パラメータ表の版管理と補間までを実装する。QCM薄層の構成、
既存CDAへの注入、スペクトル計算への適用は後続タスクとする。

## QCM距離依存パラメータの情報源（D-2確定）

- Esteban et al. (2012) の公式Supplementary Information（Supplementary
  Figures S1--S2およびSupplementary Discussion、全5ページ）を再確認した。
  Supplementary Figure S1 はNa二量体について指数関数の接続点を変えた
  頑健性検証であり、`l' = 11.76 a.u.`、`14.76 a.u.`、`5.46 a.u.` は
  いずれもNaの例である。Supplementary Figure S2もNa二量体のTDDFT/QCM比較である。
- Supplementary Discussionは大型Au球とbowtie antennaでも同様の頑健性を支持する
  と述べるだけで、Auに用いる指数関数の係数、Au向けのフィット手順、数値表、
  または生データは示していない。Naの数値をAuへ流用してはならない。
- よって、Supplementary InformationにAuの `gamma_g(l)` 数値表またはFig. 2dを
  再構成できる詳細なAu数値があるという根拠は確認できず、D-2の結論は変更しない。
- よってMVPでは、**原論文Fig. 2dのAu jelliumに対応する青色の実線**を
  デジタイズした表を暫定参照表として採用する。青色の白丸（SSTM値）は
  表の値として採用せず、曲線読取りの補助情報としてのみ扱う。

### 暫定デジタイズ表の抽出・記録

1. DOI `10.1038/ncomms1806` の公式PDFにあるFig. 2dを原図として固定し、
   取得日、ファイル識別情報、対象曲線（Au jellium・青色実線）を記録する。
2. 横軸・縦軸ごとに、両端のラベル付き目盛を主校正点、残りのラベル付き目盛を
   検証点として画像座標と物理座標の対応を求める。軸の目盛形式は原図の表示に従い、
   校正点の値とピクセル座標を抽出記録へ残す。
3. 曲線の中心線を読み取り、各点の画像座標、変換後の `l` と `gamma_g`、
   および補間方法を表に保存する。表の有効範囲外へは外挿しない。現在の
   `data/qcm/gamma_g_au_digitized.csv` は、利用者提供のWebPlotDigitizer手動読取り
   22点を版管理した暫定表である。
4. 各軸の読取誤差は、未使用の検証目盛に対する校正残差と曲線線幅の半分を
   ピクセル単位で合成し、軸変換後の `delta_l` と `delta_gamma_g` として
   各表または抽出記録に残す。数値の桁数はこの誤差を超えて主張しない。現在の
   表には校正点記録が提供されていないため、`data/qcm/metadata.yaml` にその不足を
   明記し、読取誤差は利用者提示の5--10%目安だけを保存する。

### 暫定値であることの明示

- `src/physics/qcm.py` には「暫定値：Esteban et al. (2012) Fig. 2dのAu実線を
  デジタイズした参照表。原著者のAu係数表ではない」と明記済みである。
- `src/physics/qcm.py` は `log(gamma_g)` に対するPCHIP補間だけを担い、表の上限を
  超えた場合は値を外挿せず古典極限として返す。QCM薄層化とCDA統合は未実装である。
- JSONメタデータには少なくとも `qcm_parameter_source`、
  `qcm_parameter_status`（`provisional_digitized`）、`qcm_figure`、
  `qcm_curve`、`qcm_calibration_points`、`qcm_reading_uncertainty`、
  `qcm_interpolation` を保存する。JSON出力・UI注記の実装は別タスクとする。

## モデルの物理的な考え方
QCMは、粒子間ギャップを「空の媒質」としてそのまま扱うのではなく、
ギャップ内に「トンネル電流を模した架空の導電性媒質」を配置し、
これを通常のDrudeモデルの枠組みで扱う手法である。
古典的手法とフルの量子力学的計算（TDDFT）の橋渡しとして機能する。

## 実装すべき数式（文献の式番号に対応）

1. 通常のDrude誘電関数（式1）：
   epsilon(omega) = epsilon_inf - omega_p^2 / (omega^2 + i*omega*gamma_p)

2. ギャップ内の架空媒質の静的コンダクタンス（式5、SSTM近似）：
   sigma_0(l) は、ギャップ幅 l の関数として、電子トンネル
   透過確率 T(l) から積分計算される。本ツールでは、上記のD-2決定に従い、
   Fig. 2dのAu実線をデジタイズした暫定参照表から gamma_g(l) を与える。

3. トンネル減衰定数の指数関数近似（原論文の背景）：
   gamma_g(l) は l -> 0 で gamma_g(0) = gamma_p（バルク金属の
   減衰定数）に収束し、大きな l では急速に減衰する指数関数形を取る。
   境界条件（l=0でgamma_p、透過率T(l')=0.01となる特定のl'で
   SSTM計算値に一致）が原論文で示されている。ただしAu係数とフィット手順を
   一次資料で固定できないため、MVPではこの指数関数を独自に再構成しない。

4. ギャップ内の架空媒質の誘電関数（式3）：
   epsilon(l, omega) = 1 - omega_g^2 / (omega^2 + i*omega*gamma_g(l))
   ここで omega_g = omega_p（バルク金属のプラズマ周波数）とする。

## 適用範囲と切り分け（本ツール独自の運用ルール）
文献のQCMは連続的な距離依存モデルだが、本ツールでは以下のように
離散的な運用ルールとして適用する。

- gap < 0.5 nm：計算をブロックする（QCMの適用範囲外として扱う）。
  文献のFig. 3, 4でもD<0.5 Å（接触・重なり領域）は
  QCMではなく別の扱い（contact regime, CTPモード）が必要であり、
  本ツールの多粒子CDA枠組みでは対応しない。
- 0.5 nm <= gap < 1 nm：QCMを自動適用する（tunnelling regime）。
- gap >= 1 nm：QCMを適用せず、通常のCDAで計算する
  （non-contact regime、文献のD>5 Å相当の領域概念を1 nmに
  読み替えて運用する）。

  ※ 文献の非接触領域の目安（D>5 Å、すなわち0.5 nm）と、
  本ツールが設定した「QCM適用の上限（1 nm）」は一致しない。
  これは意図的な安全マージンであり、文献の知見をそのまま
  数値流用したものではないことをコード内コメントとREADMEに明記する。

## 実装上の要求
- ギャップ領域を、複数の同心円筒状/平行平板状の薄層に離散化し、
  各層に局所的なギャップ幅 l(x,y) に応じた epsilon(l, omega) を
  割り当てる（文献のFig. 2bのn層近似に対応）。
  MVPの既定値は **4層** とする。gap 0.5、0.7、0.9 nmの同一径二量体、
  軸平行偏光で、3→4層を感度確認、4→5層を合否判定として比較する。
  `C_ext`、`C_sca`、`C_abs`の各スペクトル最大値で正規化した差とピーク高さ差は
  1%以下、ピーク位置差は波長刻み以下を実務上の目安とする。
  原論文はBEM計算で典型的に8層まで収束させており、4層はMVP向けの近似であって
  原論文と同等の収束を保証しない。4→5層で基準を満たさない場合は4層を採用しない。
- QCM適用時は、通常のCDA（多粒子dyadic Green tensor）の枠組みに
  対し、ギャップ層の誘電関数のみを差し替える形で実装し、
  ソルバー本体のアルゴリズムは変更しない。
- QCM適用の有無、適用したパラメータ（omega_p, gamma_p, 層数 n）、
  および上記の暫定デジタイズ表の出典・校正・読取誤差・補間法を
  計算結果のメタデータ（JSON）に必ず記録する。

## 検証要求
- validation_plan.mdのTest 4（極小ギャップの安全装置とQCM適用）に
  従い、gap=0.5〜1.0 nmの範囲でQCM適用前後のスペクトル変化が
  文献Fig. 3, 4に示される定性的傾向（電場増強の抑制、
  モード間の連続的な遷移）と矛盾しないことを確認する。
- 文献の数値そのもの（Na jelliumモデルの結果等）と完全一致する
  ことは初版では要求しない。定性的な傾向の一致を確認基準とする。
- 暫定デジタイズ表を使う場合は、表の有効範囲、読取誤差、
  `provisional_digitized` の状態を検証結果とメタデータに明示する。

## 明記すべき限界（README・UI双方に反映）
- 本QCM実装は、球対称ギャップに対するSSTM（static scanning
  tunnelling microscopy）近似に基づくものであり、原論文が示す
  Na/Auジェリウムモデルでの厳密なTDDFT検証結果とは異なる
  可能性がある。
- Auの距離依存パラメータは原論文Fig. 2dのデジタイズ値であり、
  著者提供の係数表または生データではない。したがって結果は暫定値として扱い、
  表の補間・読取誤差による不確かさを含む。
- 帯間遷移（interband transitions, 2.0 eV以上）の影響は、
  文献同様、本モデルのAuパラメータ（omega_p, gamma_p）には
  含まれていない。QCM適用領域と帯間遷移域（波長517 nm未満）が
  重複する場合は、既存のKreibig補正警告と合わせて二重に
  警告表示する。
