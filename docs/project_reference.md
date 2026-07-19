# Phase 2 の SI 物理式

## 位相規約と材料表現

Phase 2 は時間依存を `exp(-iωt)` とする。Johnson and Christy (1972) の材料値は
`n_p = n + i k` として読み、媒質は実数屈折率 `n_m` の均一・非吸収性媒質とする。
真空波長を `λ₀`、媒質波数を `k_m = 2πn_m / λ₀`、媒質の相対誘電率を
`ε_m = n_m²` とする。

## FCDA 分極率

半径 `a` の球について、相対屈折率 `m = n_p / n_m`、サイズパラメータ
`x = k_m a` を用いる。完全 Mie 電気双極子係数は

```text
a₁ = [m ψ₁(mx) ψ₁'(x) − ψ₁(x) ψ₁'(mx)]
     / [m ψ₁(mx) ξ₁'(x) − ξ₁(x) ψ₁'(mx)]
```

であり、SI 分極率は

```text
p = α_SI E_local
α_SI = 6π i ε₀ ε_m a₁ / k_m³
```

とする。`α_SI` の単位は `C m²/V`（`F m²`）である。完全な `a₁` を使うため、
有限サイズに由来する動的脱分極と放射反作用を Clausius–Mossotti 分極率へ別途
二重加算しない。

Kreibig 補正を明示的に有効化する場合だけ、Drude 部分を

```text
γ_R = γ_bulk + A v_F / a
ε = ε_bulk − ε_D(γ_bulk) + ε_D(γ_R)
ε_D(γ) = −ω_p² / [ω(ω + iγ)]
```

で置換する。本プロジェクトで確定しているのは `A = 1.0` と
`v_F = 1.4e6 m/s` だけであり、`ω_p` と `γ_bulk` は出典付きで呼出し側が
与えなければならない。暗黙の Au パラメータは置かない。

## 遅延 Green tensor と CDA

`R = r_i − r_j`、`R = |R|`、`R̂ = R/R` とする。自己項を除く dyadic Green tensor は

```text
G(R) = exp(i k_m R)/(4πR) [
  (1 + i/(k_mR) − 1/(k_mR)²) I
  + (−1 − 3i/(k_mR) + 3/(k_mR)²) R̂R̂
]
```

であり、単位は `m⁻¹` である。源双極子が作る電場は

```text
E(r_i) = k_m² G(r_i − r_j) p_j / (ε₀ ε_m)
```

となる。従って CDA の連立方程式は

```text
p_i − α_i Σ_{j≠i} [k_m² G(r_i−r_j)/(ε₀ε_m)] p_j = α_i E_inc(r_i)
E_inc(r) = E₀ exp(i k_m k̂·r)
```

である。

## 断面積

誘起双極子から、入射振幅 `|E₀|²` で規格化して

```text
C_ext = k_m/(ε₀ε_m|E₀|²) Im Σ_i E_inc(r_i)*·p_i
C_sca = k_m³/(ε₀²ε_m²|E₀|²)
        Re Σ_i,j p_i*·Im[G(r_i−r_j)]·p_j
C_abs = C_ext − C_sca
```

を計算する。散乱の自己項には `Im[G(0)] = k_m I/(6π)` の有限極限を使う。

## 出典

- Bohren, C. F.; Huffman, D. R. *Absorption and Scattering of Light by Small
  Particles* (1983), Chapter 4。
- Meier, M.; Wokaun, A. *Optics Letters* 8, 581–583 (1983),
  DOI: 10.1364/OL.8.000581。
- Draine, B. T.; Flatau, P. J. *JOSA A* 11, 1491–1499 (1994),
  DOI: 10.1364/JOSAA.11.001491。
- Kreibig, U.; Vollmer, M. *Optical Properties of Metal Clusters* (1995),
  DOI: 10.1007/978-3-662-09109-8。
