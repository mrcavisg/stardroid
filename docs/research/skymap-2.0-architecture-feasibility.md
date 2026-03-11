# Sky Map 2.0 — Architecture Feasibility Study

**Date:** 2026-03-11
**Scope:** Complete rewrite architectural decisions
**Context:** Hobby project, 1–2 contributors, maintainer wants to learn by building

---

## Executive Summary

Sky Map 2.0 is a from-scratch rewrite. The current codebase (1.x) is built on OpenGL ES **1.x**
(deprecated since Android 5.0 in 2014), a 1,134-line monolithic Activity, Dagger 2, and a
Java/Kotlin mix. A rewrite is not just justified — it is necessary to modernize the rendering
pipeline alone.

**Recommended stack for a 1–2 dev hobby project:**

| Area | Recommendation |
|------|---------------|
| UI | Jetpack Compose |
| Renderer | OpenGL ES 3.x (scoped AGSL experimentation) |
| KMP | No (Android-only initially) |
| DI | Hilt |
| Data | Protobuf Lite (keep) + optional Room for user data |
| Sensors | TYPE_ROTATION_VECTOR (modern, already partially in use) |

---

## 1. Baseline: What Exists Today

Before evaluating options, the current state must be understood:

| Aspect | Current State | Assessment |
|--------|--------------|------------|
| **Renderer** | OpenGL ES **1.x** (fixed-function pipeline) | Critically outdated; deprecated since API 21 |
| **Activity** | `DynamicStarMapActivity.java` — 1,134 lines | God-class, hard to test |
| **DI** | Dagger 2.48 (no Hilt) | Functional but verbose |
| **Language** | 105 Java + 79 Kotlin files | Messy split |
| **Sensors** | Legacy raw accelerometer + magnetometer fusion | `SensorOrientationController` has TODO to modernize |
| **Data** | Protobuf Lite binary assets | Compact and fast for read-only catalogs |
| **Build target** | minSdk 26 / targetSdk 36 | Good baseline |

**Key finding:** OpenGL ES 1.x uses the fixed-function pipeline (no shaders). It was deprecated in
Android 5.0 and all modern rendering APIs (Vulkan, AGSL, even OpenGL ES 2+) require a
programmable pipeline. **This means any renderer migration is a complete rewrite regardless.**

---

## 2. UI Framework

### Options

| Option | Pros | Cons |
|--------|------|------|
| **Jetpack Compose** | Modern, declarative, Kotlin-first, great for UI over renderer, excellent DX, strong community momentum, AndroidX/Google's direction | Learning curve; interop with `GLSurfaceView`/`SurfaceView` requires care |
| **Views (XML)** | Familiar, mature, no learning curve | Verbose, imperative, going stale; not what Google recommends for new projects |
| **Hybrid** | Incremental migration path | Complexity overhead; not useful for a clean rewrite |

### Sky Map-specific considerations

The sky rendering surface (OpenGL/Vulkan) lives in a `SurfaceView` or `GLSurfaceView`, **not**
in Compose's composable tree. The UI chrome (search bar, menus, info cards, settings) is
well-suited to Compose. This split is natural:

```
Compose UI layer (search, menus, overlays, info cards)
         ↕ interop
SurfaceView / GLSurfaceView (sky renderer)
```

Compose's `AndroidView` composable wraps native Views cleanly. Jetpack Compose + a native
rendering surface is a well-established pattern used in game engines, camera apps, and maps.

### Effort estimate

| Approach | Estimated effort |
|----------|-----------------|
| Views | 3–4 weeks UI work (familiar territory) |
| Compose | 4–6 weeks UI work (learning + building) |
| Hybrid | 5–7 weeks (complexity tax) |

### Recommendation: **Jetpack Compose**

The maintainer explicitly wants to learn by building. Compose is Android's future. The sky
surface is renderer-independent from the UI layer regardless of choice. Learning Compose on a
real, meaningful project is the ideal scenario. The interop story is mature and well-documented.

---

## 3. Renderer

### Options

| Option | Pros | Cons |
|--------|------|------|
| **OpenGL ES 2.0/3.x** | Well-documented, huge community, GLSurfaceView integration, NDK support, works minSdk 26+, plenty of Android examples | Older API; less performant than Vulkan |
| **OpenGL ES 3.x specifically** | Compute shaders (3.1), instanced rendering, more efficient star batch draws | Still same paradigm as 2.0; 3.0 requires API 18+, 3.1 requires API 21+ (both fine for minSdk 26) |
| **Vulkan** | Best performance ceiling, explicit GPU control, future-proof | Steep learning curve; requires API 24+; verbose (1,000s of lines for a triangle); Android Vulkan validation layer complexity |
| **AGSL / RenderEffect** | Declarative shader syntax (GLSL-like), integrates with Compose/View canvas, no GL context management | API 33+ (Android 13) only — breaks minSdk 26 promise; not designed for scene-graph rendering |
| **Compose Canvas** | Simple, integrates natively with Compose, no OpenGL needed | Cannot handle 10,000+ star draws at 60fps; no GPU acceleration for point clouds; not viable for sky map scale |

### Key analysis

**The Vulkan prototype story:** A friend of John's made a Vulkan prototype with AI assistance.
Vulkan can absolutely render a sky map — but the operational complexity is significant:

- Setup code (instance, device, swapchain, render pass, pipeline) is 2–5× more verbose than
  equivalent OpenGL ES code.
- Debugging requires understanding validation layers, SPIR-V shader compilation, and explicit
  synchronization.
- The learning investment for a solo dev who also wants to learn Compose, Hilt, and modern
  Android simultaneously is high.
- Vulkan shines for apps that push GPU limits (AAA games, complex post-processing). Sky Map
  renders point clouds, polylines, and simple textured quads — OpenGL ES 3.x handles this
  at 60fps without Vulkan's complexity.

**AGSL note:** Android GPU Shader Language is designed for `RuntimeShader` applied to `Paint`/
`Canvas`. It is excellent for visual effects (bloom on stars, night-sky atmosphere) but is NOT
a scene graph renderer. It could augment an OpenGL renderer (glow effects, atmosphere), but
cannot replace it. Also limited to Android 13+ (API 33).

**Compose Canvas:** Profiling Sky Map's current draw calls shows the renderer handles thousands
of point primitives per frame. Compose Canvas is software-rasterized (or at best hardware-
accelerated through HWUI's display list, not a GL scene graph). It will not sustain 60fps with
star counts at Sky Map scale.

### Effort estimate

| Approach | Estimated effort |
|----------|-----------------|
| OpenGL ES 2.0 | 6–8 weeks (straightforward migration from 1.x patterns) |
| OpenGL ES 3.x | 8–10 weeks (instanced rendering, compute shaders — powerful but more to learn) |
| Vulkan | 16–24 weeks for a competent Android/Vulkan dev; higher for learning-while-building |
| AGSL (as augmentation) | 2–3 weeks on top of another renderer |

### Recommendation: **OpenGL ES 3.x with optional AGSL augmentation**

OpenGL ES 3.x (API 18+, fine for minSdk 26) provides:
- Programmable shaders (fixes the core 1.x limitation)
- Instanced rendering for star fields (massive performance improvement)
- UBO/SSBO for transformation matrices
- Sufficient headroom for all Sky Map rendering needs

If John wants to experiment with Vulkan later (after the app is working), the architecture
should be designed with a renderer abstraction interface (`SkyRenderer` protocol) so the
backend can be swapped. **Do not start with Vulkan for a complete rewrite by a solo learner.**

AGSL can be added incrementally for atmosphere/glow effects on Android 13+ without touching
the core renderer.

---

## 4. Kotlin Multiplatform (KMP)

### What KMP would share

The astronomical computation layer is genuinely platform-agnostic:
- Ephemeris calculations (planet positions, rise/set times)
- Coordinate transformations (RA/Dec ↔ alt/az, equatorial ↔ ecliptic)
- Star catalog data models
- Time math (Julian dates, sidereal time)

This maps to roughly 20–30% of the current codebase.

### Trade-offs

| Consideration | Android-only Kotlin | KMP (Android + iOS) |
|---------------|--------------------|--------------------|
| **Setup complexity** | None | Significant; expect 2–4 weeks for build config, toolchain, expect/actual declarations |
| **iOS rendering** | N/A | Requires separate Metal/SwiftUI work (not shared via KMP) |
| **iOS sensor access** | N/A | Separate CoreMotion wrapper |
| **Shared benefit** | — | ~20–30% of code shared |
| **Testing** | JVM unit tests | KMP requires Kotlin/Native test infra |
| **CI complexity** | Android only | Must add macOS runners, Xcode builds |
| **Solo dev overhead** | Low | High — doubles the platform surface |
| **Existing iOS competition** | N/A | SkySafari, Sky Guide are mature; hard to compete |

### Recommendation: **Skip KMP for 2.0**

For a hobby project with 1–2 contributors doing a complete rewrite, KMP adds substantial
overhead before the Android app even works. The astronomical math layer should be architected
as a clean Kotlin module (`astro-core/`) with no Android dependencies — this makes future
KMP migration trivial if desired. **Decouple first, multiplatform later.**

Architecture suggestion:
```
:app (Android)
:astro-core (pure Kotlin, no Android deps) ← KMP-ready when needed
:datamodel (protobuf)
```

---

## 5. Dependency Injection

### Options

| Option | Pros | Cons |
|--------|------|------|
| **Hilt** | Dagger under the hood (familiar), Android lifecycle-aware, standard entry points, excellent documentation, Google-recommended | Annotation processing (kapt/KSP); some magic for beginners |
| **Koin** | Service locator (not true DI), no annotation processing, simpler syntax, easier to learn | Runtime errors vs compile-time; not true DI (can leak); less performant |
| **Manual DI** | Full control, zero overhead, easy to understand | Boilerplate explodes as app grows; no lifecycle management |
| **Dagger 2 (keep)** | Already in use | Not Android lifecycle-aware; verbose modules; harder to test than Hilt |

### Current pain point

`AGENTS.md` documents the `@PerActivity` scoping pitfall with `MediaPlayer` and file handles.
Hilt's `@ActivityRetainedScoped`, `@ViewModelScoped`, and `@ActivityScoped` provide explicit,
well-documented lifecycle semantics that eliminate this class of bug.

### Recommendation: **Hilt**

For a 1–2 dev hobby project rewriting from scratch, Hilt is the right call:
- Migrating from Dagger 2 concepts to Hilt is straightforward (Hilt is Dagger under the hood)
- `@HiltViewModel` + ViewModel architecture replaces the God-Activity pattern
- Lifecycle-aware scopes prevent the `@PerActivity` pitfall documented in AGENTS.md
- If switching to KSP (instead of kapt), build times improve significantly

---

## 6. Astronomical Data Storage

### Current state

Binary Protobuf assets loaded at runtime via `AbstractFileBasedLayer`. The data pipeline:
```
Star catalogs → tools/Main.java → ASCII proto → binary proto → assets/
```

This is read-only catalog data. It works well.

### Options

| Option | Use case | Pros | Cons |
|--------|----------|------|------|
| **Protobuf Lite (keep)** | Read-only catalogs | Fast binary parsing, no reflection, compact | Write operations are awkward |
| **Room/SQLite** | User data (saved objects, observations, custom locations) | Android-standard, query support, reactive (Flow) | Overkill for immutable catalogs; schema migrations |
| **JSON assets** | Catalogs | Human-readable, easy tooling | Slow parsing at scale; ~3× size vs binary |
| **Hipparcos/Tycho-2 migration** | Larger star catalog | More stars (118k+ vs current ~1,500 bright stars) | Data pipeline rewrite; app size increase; render performance impact |

### Recommendation: **Two-layer approach**

- **Protobuf Lite** for immutable catalogs (stars, constellations, Messier objects) — keep the
  current approach, just rebuild the data pipeline in Kotlin.
- **Room** for mutable user data (custom locations, observation logs, saved searches).
- **Catalog expansion** (Hipparcos/Tycho-2): consider for 2.0 if the renderer can handle it
  efficiently with instanced rendering. Tycho-2 has ~2.5M stars; a magnitude cutoff at ~7.5
  reduces this to ~10,000 visible-to-naked-eye stars — very manageable with GPU instancing.

---

## 7. Sensor Pipeline

### Current state

`SensorOrientationController.java` has a TODO comment: *"this class needs to be refactored to
use the new sensor API"*. It uses:
- `TYPE_ACCELEROMETER` + `TYPE_MAGNETIC_FIELD` with manual Kalman-like smoothing
- Falls back correctly, but the sensor fusion is done in app code

The modern Android approach:
- `TYPE_ROTATION_VECTOR` (fused by hardware/OS, API 9+)
- `TYPE_GAME_ROTATION_VECTOR` (no magnetometer, better for interior use)
- `SensorManager.getRotationMatrixFromVector()` → ready-made rotation matrix

`AstronomerModelImpl.kt` already references `TYPE_ROTATION_VECTOR` — the groundwork exists.

### AR Mode Consideration

The ticket asks about camera integration for a "real AR mode":

| Approach | Notes |
|----------|-------|
| **ARCore** | Google's AR platform; excellent plane detection + pose tracking; requires `gms` flavor; API 24+ |
| **Camera2 + sensor overlay** | Manual approach; just render sky overlay on camera preview; simpler, works on both flavors |
| **CameraX** | Lifecycle-aware camera; good for `fdroid` flavor; no AR tracking |

For 2.0, a simple camera preview + sky overlay (no ARCore) is achievable in 2–3 weeks and
works on both flavors. Full ARCore is a separate feature milestone.

### Recommendation

Use `TYPE_ROTATION_VECTOR` exclusively in 2.0 (minSdk 26 is well above API 9 where it became
reliable). The `astro-core` module should remain sensor-agnostic — sensors feed a
transformation matrix into the astronomical model.

---

## 8. Decision Summary Matrix

| Area | Option A | Option B | Option C | **Recommendation** |
|------|----------|----------|----------|--------------------|
| UI | Views (familiar) | **Compose** ✓ | Hybrid | **Compose** |
| Renderer | OpenGL ES 2.0 | **OpenGL ES 3.x** ✓ | Vulkan | **OpenGL ES 3.x** |
| KMP | **Android-only** ✓ | KMP (Android+iOS) | — | **Android-only** |
| DI | Dagger 2 (keep) | **Hilt** ✓ | Koin | **Hilt** |
| Catalog data | **Protobuf Lite** ✓ | JSON assets | Room | **Protobuf Lite** |
| User data | SharedPreferences | **Room** ✓ | — | **Room** |
| Sensors | Raw accel+mag | **TYPE_ROTATION_VECTOR** ✓ | ARCore | **Rotation Vector** |
| Language | Java | **Kotlin-only** ✓ | — | **Kotlin-only** |

---

## 9. Recommended Architecture for 2.0

```
:app
├── ui/           (Compose screens, ViewModels, Hilt entry points)
├── renderer/     (OpenGL ES 3.x SkyRenderer, SurfaceView bridge)
├── sensors/      (SensorOrientationController using TYPE_ROTATION_VECTOR)
├── layers/       (12 sky layers, rewritten in Kotlin)
└── di/           (Hilt modules)

:astro-core  (pure Kotlin, zero Android deps — KMP-ready)
├── ephemeris/    (planet positions, solar system)
├── coordinates/  (RA/Dec, alt/az, equatorial transformations)
├── catalog/      (data model for stars, DSOs, constellations)
└── time/         (Julian dates, sidereal time)

:datamodel   (Protocol Buffer definitions, keep as-is)

:tools       (data generation pipeline, rewrite in Kotlin)
```

### ViewModel pattern (replaces God-Activity)

```
DynamicStarMapActivity
  └── SkyMapViewModel (Hilt @HiltViewModel)
        ├── observes sensor orientation
        ├── drives renderer via StateFlow
        └── manages search, time travel, layer visibility

Compose UI tree
  └── AndroidView { GLSurfaceView (renderer surface) }
  └── SearchBar, InfoCard, MenuOverlay (Compose)
```

---

## 10. Effort Estimates

| Work stream | Estimated weeks | Notes |
|-------------|----------------|-------|
| Project setup (modules, Hilt, build) | 1–2 | Straightforward |
| `astro-core` module extraction | 3–4 | Port AstronomerModel, ephemeris, coordinates to pure Kotlin |
| OpenGL ES 3.x renderer | 6–10 | Most complex; new shaders, instancing, all 12 layers |
| Compose UI layer | 4–6 | Search, info cards, menus, settings, night mode |
| Sensor pipeline (rotation vector) | 1–2 | Mostly deleting old code |
| Data pipeline rewrite (Kotlin tools) | 2–3 | Port tools/Main.java to Kotlin |
| Testing infrastructure | 2–3 | JUnit 5 + Robolectric + Compose testing |
| **Total (optimistic, solo)** | **19–30 weeks** | ~5–7 months part-time |
| **Total (realistic, learning)** | **30–50 weeks** | ~8–12 months part-time |

The renderer is the long pole. OpenGL ES 3.x shaders for star rendering (with correct
magnitude-to-size mapping, color temperature, constellation line rendering) are non-trivial.

---

## 11. Learning Path Recommendation

Since John explicitly wants to learn while building (not have AI write everything), a suggested
learning sequence:

1. **Week 1–2:** Jetpack Compose fundamentals (official Compose pathway)
2. **Week 3–4:** Hilt + ViewModel + StateFlow patterns
3. **Week 5–6:** OpenGL ES 2.0 basics (learnopengl.com, Android OpenGL tutorials)
4. **Week 7–8:** Upgrade to OpenGL ES 3.x (instancing, shaders)
5. **Week 9+:** Build incrementally, layer by layer

Start with one working star layer before building all 12. Get the rotation-to-sky-coordinates
math working early — it's the hardest conceptual piece and everything depends on it.

---

## References

- Sky Map 1.x source: https://github.com/sky-map-team/stardroid
- `app/build.gradle` — confirmed Dagger 2.48, minSdk 26, no Compose, no Vulkan
- `specs/rendering/README.md` — confirms OpenGL ES **1.x** (fixed-function)
- `app/src/main/java/.../control/SensorOrientationController.java` — TODO: modernize sensors
- `app/src/main/java/.../activities/DynamicStarMapActivity.java` — 1,134 lines (monolithic)
- Android developer docs: https://developer.android.com/develop/ui/compose
- Android Vulkan guide: https://developer.android.com/games/develop/use-vulkan
- Android AGSL: https://developer.android.com/develop/ui/views/graphics/agsl
- KMP docs: https://kotlinlang.org/docs/multiplatform.html
- Hilt guide: https://developer.android.com/training/dependency-injection/hilt-android
- learnopengl.com — best OpenGL ES learning resource
