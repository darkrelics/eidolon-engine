package main

import (
	crypto_rand "crypto/rand"
	"encoding/binary"
	"math"
)

// Tunables: adjust to taste.
const (
	kShift = 0.20 // mean shift per rating step
	kVar   = 0.35 // maximum ±fractional change in σ
	minSig = 0.25 // absolute floor for σ (safety‑net)
)

// Outcome is the bare mechanical result.
// Sigma  > 0 ⇒ aggressor wins; < 0 ⇒ aggressor fails.
type Outcome struct {
	Sigma   float64
	Success bool
}

// ResolveOpposedCheck performs one opposed check using the bounded
// mean‑shift + variance‑stretch model and cryptographically secure RNG.
func ResolveOpposedCheck(aggressor, defender int) Outcome {
	delta := aggressor - defender
	mu := kShift * float64(delta)

	// σ widens or narrows smoothly but never leaves [minSig, 1+kVar].
	sigma := 1 + kVar*math.Tanh(float64(delta)/10)
	if sigma < minSig {
		sigma = minSig
	}

	z := cryptoNormal()    // N(0,1) from crypto/rand
	zPrime := mu + sigma*z // affine transform

	return Outcome{
		Sigma:   zPrime,
		Success: zPrime >= 0,
	}
}

// ResolveStaticCheck performs a check against a fixed difficulty
// using the same mechanics as opposed checks but with a static defender value
func ResolveStaticCheck(aggressor, difficulty int) Outcome {
	return ResolveOpposedCheck(aggressor, difficulty)
}

// cryptoNormal returns a single N(0,1) sample using Box–Muller and crypto/rand.
func cryptoNormal() float64 {
	u1 := secureUniform()
	u2 := secureUniform()

	// Box–Muller transform
	r := math.Sqrt(-2 * math.Log(u1))
	theta := 2 * math.Pi * u2

	return r * math.Cos(theta)
}

// secureUniform returns a float64 in (0,1) generated from 53 random bits.
func secureUniform() float64 {
	var buf [8]byte
	_, err := crypto_rand.Read(buf[:])
	if err != nil {
		panic("crypto/rand failure: " + err.Error())
	}
	x := binary.LittleEndian.Uint64(buf[:]) >> 11 // keep top 53 bits
	return float64(x) / (1 << 53)
}
