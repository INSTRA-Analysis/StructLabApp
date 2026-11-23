# 8. Design checks and Optimise

StructLab checks each member against its resistance for the result set on screen, and can
choose the lightest steel angle for each group of a lattice structure. The checks are a tool
for sizing and for spotting critical members; they are not a complete code check, and this
chapter says exactly what each one covers.

## 8.1 Which check a member gets

The material is taken from the member's E: 20 to 45 GPa is concrete, 8 to 16 GPa is timber,
anything else is steel.

| Member | Check | Basis |
|---|---|---|
| Steel **equal angle** from the library | Buckling, tension and bending of the angle (8.2) | EN 1993-1-1 |
| Any other **steel** section | Cross-section resistance only, **no buckling** | EN 1993-1-1 6.2 |
| **Concrete** with reinforcement data | Bending and axial resistance of the section | EN 1992-1-1 6.1 |
| **Timber** | Bending only | |

An angle is recognised when its area and minor moment of inertia match an angle in the
library; anything else is never assumed to be an angle. The tooltip and the Design table always
say which basis a utilisation comes from, so a cross-section-only figure is never mistaken for
a buckling check.

The strength comes from the member's material (fy for steel, fck and fyk for concrete). The
member's **Design** tab holds what the checks need: W_pl and W_el for steel sections, and for
concrete the width b, depth h, cover, tension reinforcement As and fyk.

## 8.2 Steel angles (EN 1993-1-1)

| Force | Check | Resistance |
|---|---|---|
| **Compression** | Flexural buckling about the minor (v) axis, 6.3.1, buckling curve b | N<sub>b,Rd</sub> = χ A fy / γM1 |
| **Tension** | Yielding of the gross section, 6.2.3(2)(a) | N<sub>pl,Rd</sub> = A fy / γM0 |
| **Bending** (beam members) | Elastic bending resistance | M<sub>Rd</sub> = W<sub>el,min</sub> fy / γM0 |

- The buckling length is the member length between nodes, or the shorter length to a
  crossing (8.4).
- γM0 = γM1 = 1.0, the recommended values; your National Annex may differ.
- When a member carries both axial force and bending, the two ratios are **added** as an
  indication; the interaction factors of 6.3.3 are not applied.
- An angle that is Class 4 in compression in its steel grade is reported as *not checked*:
  the effective-section check is not implemented.

**Not checked:** torsional-flexural buckling, the eccentricity of single-leg end connections
(EN 1993-3-1), the net section through bolt holes, and the connections themselves.

## 8.3 Other sections

- **Other steel sections**: N / (A fy) + M / (W<sub>pl</sub> fy), the cross-section only,
  with no buckling. Use it for members whose stability you check separately.
- **Concrete**: the bending resistance of a rectangular section with tension reinforcement
  (γc = 1.5, γs = 1.15), and the axial resistance A<sub>c</sub> f<sub>cd</sub> + A<sub>s</sub>
  f<sub>yd</sub> in compression, A<sub>s</sub> f<sub>yd</sub> in tension. Second-order effects
  in slender columns (EN 1992-1-1 5.8) are not checked.

## 8.4 Crossing bracing

In a lattice tower the diagonals cross. Where a diagonal in compression is crossed by one in
tension, and the two are bolted together at the crossing, the tension member holds the
compressed one there, and its buckling length is the distance to the crossing rather than its
full length.

**Model → Crossing Bracing Connected** turns this assumption on. It changes only the buckling
length used by the design checks, member by member and combination by combination; the
analysis is unchanged. Turn it on only where the bracing really is connected at the
crossings.

## 8.5 Reading the checks

- The **Design** tab of the Results panel lists every check with its design force, resistance,
  utilisation η and PASS or FAIL (chapter 7.3).
- **Results → Utilisation** colours the members by η, and the hover tooltip gives η and the
  governing check.
- Both follow the result set: to check a combination, solve it and choose it in
  **Result Set**. For a full design, solve all the ULS combinations and look at each, or use
  Optimise, which checks them all.

## 8.6 Optimise

Optimise chooses the lightest equal angle for each **group** of members so that every member
stays under a target utilisation in **every ULS combination**. Changing a section changes the
stiffness and so the forces; Optimise re-solves and repeats until the choice stops changing.

- Members of a group always share one section.
- Only groups whose members are all library angles are changed; others are reported as
  skipped.
- Groups you list in order (for example tower legs from the base up) stay in size order: a
  higher leg is never heavier than the one below it.
- You can set the smallest section allowed and a slenderness limit L / i<sub>v</sub> of your
  own (not one taken from a code).

Optimise is not on the ribbon yet; it runs as a script from the StructLab folder:

```bash
python examples/optimise_groups_demo.py model.slab optimised.slab --target 0.85
```

| Option | Meaning |
|---|---|
| `--target 0.85` | Utilisation every member must stay under (default 0.85) |
| `--min "L 50×5"` | Smallest section allowed |
| `--slenderness 200` | Largest L / i<sub>v</sub> allowed |
| `--crossing-braces` | Treat crossing bracing as connected (8.4) |

The script regenerates the EN 1990 combinations from the load cases, keeps tower leg groups
named *Leg 1 (base)* to *Leg 4 (top)* in order, and saves the result to the second file; the
input file is not changed. It prints, for each group, the section and utilisation before and
after and what governs, then the total steel mass before and after and whether the choice
converged.

Optimise relies on the angle check of 8.2 and has the same limits. Check the final design,
including the connections, by your usual means.
