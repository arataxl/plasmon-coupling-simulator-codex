# 参照資料

## 初版で使う根拠

1. Mie理論
   - Bohren, C. F.; Huffman, D. R.
     Absorption and Scattering of Light by Small Particles.
   - 用途：単一球のExtinction、Scattering、Absorptionの定義と参照解

2. Au光学定数
   - Johnson, P. B.; Christy, R. W.
     Optical Constants of the Noble Metals.
     Physical Review B 6, 4370–4379 (1972).
   - 用途：Auのバルク複素屈折率 n, k
   - 注意：ナノ粒子そのものではなく、バルク由来の光学定数である

3. DDAと適用範囲
   - Draine, B. T.; Flatau, P. J.
     User Guide for the Discrete Dipole Approximation Code DDSCAT.
   - 用途：任意形状の精密参照計算を将来導入する際の候補
   - 注意：初版の高速CDA計算へDDSCATを直接組み込まない

4. BEMによる精密参照
   - Hohenester, U.; Trügler, A.
     MNPBEM – A Matlab toolbox for the simulation of plasmonic nanoparticles.
     Computer Physics Communications 183, 370–381 (2012).
   - 用途：将来的なナノスター、ナノキャップ、少数粒子系の精密検証
   - 注意：初版の必須依存関係にはしない