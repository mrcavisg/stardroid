# Sky Map — Análise de Reviews Negativas: Pain Points e Oportunidades

> **Data:** Março 2026
> **Fontes:** GitHub Issues (sky-map-team/stardroid), Google Play Store, Space.com, Slant, análise do codebase

---

## Sumário Executivo

Sky Map (4.02★ em ~470k avaliações no Play Store) é bem considerado como ponto de entrada para astronomia amadora, mas sofre de um conjunto recorrente de reclamações centradas em **sensores mal calibrados**, **UI datada** e **descoberta de features**. Comparado aos concorrentes diretos (Stellarium Mobile Plus, Star Walk 2, SkyView), o app perde principalmente em polimento visual e breadth de features. A boa notícia: a infraestrutura interna de sensores é robusta — o problema de UX é que os usuários não sabem como usá-la.

---

## Top 10 Pain Points (ranqueados por frequência/impacto)

| # | Pain Point | Frequência | Impacto | Fontes |
|---|-----------|-----------|---------|--------|
| 1 | **Calibração de bússola constante / mapa gira ou treme** | Muito alta | Crítico | GitHub #533, Play Store reviews, Space.com |
| 2 | **App parece quebrado em devices sem gyroscope ou sem bússola** | Alta | Crítico | GitHub #153, #174, #19 |
| 3 | **UI datada — visual e UX não competitivos** | Alta | Alto | Space.com 3.5/5, Slant, Stellarium comparison |
| 4 | **Crashes ("Sky Map has stopped")** | Alta | Alto | GitHub #667, #622, Play Store |
| 5 | **Norte/Sul aparecendo na posição errada (horizonte)** | Média-alta | Alto | GitHub #545 — Pixel 7 Pro, julho 2025 |
| 6 | **Night mode escurece demais / brilho não responde** | Média | Médio | Play Store reviews 2024-2025 |
| 7 | **Features escondidas / baixa descoberta (time travel, layers, modo manual)** | Média | Médio | GitHub #690, maintainer relato (3x usage after move) |
| 8 | **Catálogo limitado de objetos — falta deep sky objects, asteroides, cometas** | Média | Médio | GitHub #651, comparação Stellarium |
| 9 | **Ausência de controle de telescópio** | Baixa-média | Baixo no legado | GitHub #543, Stellarium feature |
| 10 | **Sem notificações / calendário de eventos astronômicos** | Baixa-média | Baixo no legado | Comparação Star Walk 2 |

---

## 1. Sensor Pain Points — Análise Detalhada

### O que os usuários reclamam

- "Tenho que calibrar a bússola toda vez que abro o app"
- "O mapa gira e treme sozinho, não consigo apontar para nada"
- "Norte e Sul estão no horizonte — está completamente errado" (Pixel 7 Pro, issue #545, julho 2025)
- "App oversensitive — qualquer movimento pequeno causa rotação exagerada" (issue #533, janeiro 2025)
- App acusa erro de sensores em devices que tecnicamente têm os sensores, mas mal calibrados (#174)

### O que o codebase já tem (positivo)

O app tem infraestrutura sólida de sensores que a maioria dos usuários nunca descobre:

| Componente | O que faz |
|-----------|-----------|
| `CompassCalibrationActivity` | Guia o usuário na calibração figura-8 com animação e feedback de accuracy em tempo real |
| `NoSensorsDialogFragment` | Alerta sobre sensores ausentes (com opção "don't show again") |
| `DiagnosticActivity` | Painel completo: acelerômetro, bússola, giroscópio, rotation vector, GPS — com cores de status |
| `SensorOrientationController` | Fallback chain: RotationVector → Accel+Mag+Gyro → Accel+Mag → Manual |
| `SensorDamping` | Filtro de suavização configurável (SLOW/STANDARD/FAST, damping 0.3–0.9) |
| Manual mode | Navegação por toque quando sensores ausentes |

### Fallback chain atual

```
TYPE_ROTATION_VECTOR (preferido — fused, ~70% dos devices)
    └─ indisponível → Acelerômetro + Magnetômetro + Giroscópio
                          └─ sem gyro → Acelerômetro + Magnetômetro
                                             └─ sem mag → Modo Manual apenas
```

### Problema real de UX

A calibração existe mas é **reativa** (aparece depois que o problema ocorre) e **escondida** (usuários chegam no Play Store sem saber o que fazer). O `CompassCalibrationActivity` é excelente — mas nenhum novo usuário sabe que existe.

**John estava certo:** o problema frequentemente não é o app, é o device (bússola com interferência magnética — metal, capas com ímãs, carros). O app não comunica isso claramente.

---

## 2. Feature Requests Mais Comuns (GitHub Issues)

| Feature | Issues | Prioridade sugerida |
|---------|--------|-------------------|
| Warm Welcome / onboarding flow | #690 (criado Mar 2026) | Quick-win legado |
| Catálogo expandido (deep sky, asteroides) | #651, #627, #645 | v2.0 |
| Info cards para todos os objetos nomeados | #645, #627 | v1.0 continuação |
| Controle de telescópio | #543 | v2.0 |
| Modo Cardboard/VR | #537 | v2.0 |
| Filtro por magnitude | triage #599 | v1.0 quick-win |
| Ícone adaptativo | triage #599 | Quick-win imediato |
| Busca por coordenadas (RA/Dec) | #596 | v1.0 |
| Salvar locais favoritos | triage | v1.0 |
| Material You / M3 | arquitetura | v1.0 / v2.0 |

---

## 3. Matriz de Features: Sky Map vs Concorrentes

| Feature | Sky Map | Stellarium Mobile Plus | Star Walk 2 | SkyView |
|---------|---------|----------------------|-------------|---------|
| **Custo base** | Grátis | Grátis (Plus pago) | Grátis (Plus pago) | Grátis (Lite) |
| **Rating Play Store** | 4.02★ (~470k) | 4.3★ | 4.7★ (~540k) | 4.3★ |
| **AR com câmera** | Limitado (sem overlay real) | ✅ (adicionado recentemente) | ✅ | ✅ |
| **Catálogo de estrelas** | ~9k estrelas (binárias) | 600k grátis / 1.69B Plus | Abrangente | Abrangente |
| **Deep sky objects** | Messier + alguns NGC | 80k grátis / 2M Plus | Sim | Sim |
| **Telescópio control** | ❌ | ✅ (Bluetooth/WiFi) | ❌ | ❌ |
| **Eventos/calendário** | ❌ | ✅ | ✅ | Parcial |
| **Rastreamento de satélites** | ISS apenas | ✅ | ✅ | ✅ |
| **Offline completo** | ✅ | ✅ (dados reduzidos) | Parcial | ❌ |
| **Open source / FOSS** | ✅ | ❌ | ❌ | ❌ |
| **Night mode** | ✅ | ✅ | ✅ | ✅ |
| **Modo manual (sem sensores)** | ✅ | ✅ | Parcial | Parcial |
| **Diagnóstico de sensores** | ✅ (DiagnosticActivity) | ❌ | ❌ | ❌ |
| **Onboarding/tutorial** | ❌ (apenas WhatsNew) | ✅ | ✅ | ✅ |
| **Zoom/magnificação** | Básico | Avançado | Avançado | Avançado |
| **Time Travel** | ✅ | ✅ | Parcial | ❌ |

**Vantagens únicas do Sky Map:**
- Único totalmente gratuito e open source
- `DiagnosticActivity` — nenhum concorrente tem diagnóstico de sensores tão detalhado
- Leveza — não exige hardware potente
- Modo manual robusto para devices sem sensores

**Lacunas críticas:**
- AR com câmera (todos concorrentes têm)
- Onboarding (todos concorrentes têm)
- Catálogo pequeno comparado ao Stellarium

---

## 4. Oportunidades Quick-Win (app legado v1.x)

Ordenadas por **impacto / esforço**:

### 🥇 Tier 1 — Máximo impacto, mínimo esforço

| # | Oportunidade | Esforço | Impacto esperado | Obs |
|---|-------------|---------|-----------------|-----|
| 1 | **Warm Welcome Screen** (issue #690) | Médio (~3 dias) | Alto — reduz churn de novos usuários que acham o app quebrado | Reutiliza mecanismo do WhatsNewDialog; inclui sensor setup |
| 2 | **Melhorar mensagem de erro de sensor** — explicar que é o phone, não o app | Baixo (~1 dia) | Alto — reduz reviews 1★ sobre "compass broken" | Editar strings em `NoSensorsDialogFragment` e `CompassCalibrationActivity` |
| 3 | **Fix crashes (#667, #622)** | Médio | Alto — crashes são kill direto de rating | Investigar reports no Play Console |
| 4 | **Fix North/South inaccuracy (#545)** | Médio | Alto — bug crítico reportado em Pixel 7 Pro (device popular) | Verificar cálculo de zenith em `AstronomerModel` |
| 5 | **Ícone adaptativo** | Baixo (~2h) | Médio — polimento visual, aparece em launchers modernos | Simples asset change |

### 🥈 Tier 2 — Alto impacto, esforço médio

| # | Oportunidade | Esforço | Impacto esperado |
|---|-------------|---------|-----------------|
| 6 | **Fix night mode dimness** | Baixo-médio | Médio — reclamação frequente, fácil de reproduzir |
| 7 | **Calibração proativa no onboarding** — não esperar SENSOR_STATUS_UNRELIABLE | Médio | Alto — calibrar antes do problema, não depois |
| 8 | **Adicionar dica visual sobre features** (tooltip primeira vez para time travel, layers) | Médio | Médio — baseado no relato de uso 3x após mover time travel |
| 9 | **Ajustar sensor damping padrão** — issue #533 oversensitivity | Baixo | Médio — apenas ajuste de constante no default |
| 10 | **Filtro por magnitude** | Médio | Médio — pedido frequente, útil para céus urbanos |

### 🥉 Tier 3 — Reservar para v2.0

| Oportunidade | Motivo |
|-------------|--------|
| AR com câmera overlay | Exige nova arquitetura de rendering |
| Telescópio control | Bluetooth stack complexo |
| Catálogo expandido (bilhões de estrelas) | Exige novo pipeline de dados |
| Eventos/calendário astronômico | Exige backend ou dados offline volumosos |
| Material Design 3 completo | Refactor de UI significativo, melhor feito no v2.0 |

---

## 5. Spec Inicial — Warm Welcome Screen

### Contexto

O `SplashScreenActivity` já gerencia a sequência de entrada: EULA → WhatsNew → DynamicStarMapActivity. O `WhatsNewDialogFragment` usa um WebView com HTML injetado e é mostrado uma vez por versão via `READ_WHATS_NEW_PREF_VERSION`.

### Proposta de Arquitetura

**Trigger:** Primeira execução após instalação (não a cada update). Separar da lógica de WhatsNew via nova preference key: `WARM_WELCOME_SHOWN`.

**Fluxo:**
```
SplashScreen
    ├── (primeira vez) → WarmWelcomeActivity (multi-step)
    │       Step 1: Apresentação — "Aponte para o céu"
    │       Step 2: Sensores — "Como funciona a bússola"
    │       Step 3: Calibração — "Se o mapa tremeu, faça isso"
    │       Step 4: Modo manual — "Sem bússola? Use assim"
    │       Step 5: Features principais — Time Travel, Layers, Busca
    │       [Skip disponível em todos os steps]
    └── → DynamicStarMapActivity
```

### Requisitos Funcionais

| Req | Descrição |
|----|-----------|
| WW-01 | Exibir apenas na primeira execução pós-instalação |
| WW-02 | Skippable — botão "Pular" sempre visível |
| WW-03 | 5 steps máximo para não cansar |
| WW-04 | Step de sensores deve checar hardware presente e adaptar mensagem |
| WW-05 | Step de calibração deve mostrar animação figura-8 (reutilizar asset de `CompassCalibrationActivity`) |
| WW-06 | Step de modo manual deve aparecer com destaque em devices sem magnetômetro |
| WW-07 | Compatível com night mode |
| WW-08 | Strings devem ser localizáveis (evitar texto em imagens) |
| WW-09 | Reutilizar screenshots/assets na documentação de ajuda |
| WW-10 | Analytics: tracking de completion rate e step de abandono |

### Conteúdo por Step

**Step 1 — Apresentação**
- Título: "Bem-vindo ao Sky Map"
- Texto: "Aponte seu celular para qualquer parte do céu. Usando os sensores do seu dispositivo, o Sky Map mostra exatamente o que está na direção que você olha."
- Visual: screenshot do mapa apontado para o céu

**Step 2 — Como os sensores funcionam**
- Título: "Bússola e giroscópio"
- Texto: "O Sky Map usa a bússola do seu celular para saber para onde você está apontando. Às vezes, a bússola precisa ser calibrada — especialmente perto de superfícies metálicas ou capas magnéticas."
- Visual: animação do eixo de rotação

**Step 3 — Calibração**
- Título: "Se o mapa parecer errado..."
- Texto: "Mova o celular em um movimento de figura-8 para calibrar a bússola. Você pode fazer isso a qualquer momento pelo menu."
- Visual: animação figura-8 (já existe em `CompassCalibrationActivity`)
- Ação inline: botão "Calibrar agora" → `CompassCalibrationActivity`

**Step 4 — Sem bússola? (condicional)**
- Exibir apenas se `TYPE_MAGNETIC_FIELD == null`
- Título: "Seu dispositivo não tem bússola"
- Texto: "Sem problema — você pode navegar pelo mapa com o toque. Use dois dedos para rotacionar e explorar o céu manualmente."
- Visual: demonstração do gesture de rotação

**Step 5 — Discover features**
- Título: "Mais para explorar"
- 3 cards: Time Travel (relógio), Camadas (layers), Busca (lupa)
- Texto curto em cada card descrevendo o que faz

### Notas Técnicas

- Reutilizar o padrão de `WhatsNewDialogFragment` (WebView + HTML) OU criar `Activity` própria com `ViewPager2` (recomendado para melhor controle de animação e acessibilidade)
- `ViewPager2` + `RecyclerView.Adapter` permite steps nativos sem WebView
- Testar com `TalkBack` ativo (acessibilidade)
- A preference `WARM_WELCOME_SHOWN` deve ser setada **após** o usuário completar ou pular, nunca antes

---

## 6. Conclusões e Recomendações Priorizadas

### Para o app legado (v1.x) — próximos 3 meses

1. **Implementar Warm Welcome** (#690) — alta prioridade. É o item de maior retorno por dollar: endereça diretamente o maior pain point (sensores confusos para novos usuários) e melhora a primeira impressão contra concorrentes que todos têm onboarding.

2. **Fix crashes** (#667, #622) — máxima urgência. Crashes são reviews 1★ automáticos. Investigar Play Console crash reports.

3. **Fix North/South bug** (#545) — coordenação incorreta em Pixel 7 Pro (device muito comum). Pode ser regression introduzida nos últimos 12 meses.

4. **Melhorar comunicação de sensor errors** — mudar mensagem do `NoSensorsDialogFragment` e da calibração para deixar claro que o problema é do hardware do device, não do app. Simples, alto impacto em percepção.

5. **Ajustar sensor damping default** (#533) — reduzir oversensitivity ajustando o damping factor padrão. Mudança de uma linha.

### Para v2.0 — reservar

- AR real com câmera overlay (diferencial competitivo #1 que falta)
- Catálogo expandido (1B+ estrelas via Gaia DR2)
- Material Design 3 completo
- Telescópio control (nicho mas diferencial de poder)
- Calendário de eventos astronômicos

---

## Referências

- GitHub Issues: https://github.com/sky-map-team/stardroid/issues
- ISSUES_ANALYSIS.md: https://github.com/sky-map-team/stardroid/blob/master/ISSUES_ANALYSIS.md
- Issue #690 (Warm Welcome): https://github.com/sky-map-team/stardroid/issues/690
- Issue #545 (North/South inaccurate): https://github.com/sky-map-team/stardroid/issues/545
- Issue #533 (Oversensitive): https://github.com/sky-map-team/stardroid/issues/533
- Issue #153 (Missing gyro detection): https://github.com/sky-map-team/stardroid/issues/153
- Space.com Review (3.5/5): https://www.space.com/sky-map-stargazing-app-review
- Stellarium Mobile features: https://stellarium-labs.com/stellarium-mobile-plus/
- Star Walk 2 comparison: https://vitotechnology.com/news/how-to-choose-a-stargazing-app
- Best stargazing apps 2026: https://www.space.com/best-stargazing-apps
- Codebase: `app/src/main/java/com/google/android/stardroid/activities/CompassCalibrationActivity.java`
- Codebase: `app/src/main/java/com/google/android/stardroid/activities/dialogs/NoSensorsDialogFragment.java`
- Codebase: `app/src/main/java/com/google/android/stardroid/activities/DiagnosticActivity.java`
- Codebase: `app/src/main/java/com/google/android/stardroid/activities/SplashScreenActivity.java`
