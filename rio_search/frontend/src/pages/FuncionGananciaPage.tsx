import { Panel } from '../components/ui/Panel'
import { Badge } from '../components/ui/Badge'
import tableStyles from '../styles/table.module.css'
import styles from './FuncionGananciaPage.module.css'

// Contenido portado de docs/referencia_funcion_y_dataset.html (hoja de referencia A4, worktree
// principal) — misma fuente que usa el equipo para discutir criterios con el codirector.
// Referencias de NSE/KGE tomadas literal de research/catalog/*.yaml, no inventadas.

const TAU_ROWS = [
  { tau: '0,85', castiga: 'subestimar', cociente: '5,7×', lectura: 'crecida plena: quedarse corto es lo caro', dias: '11,7' },
  { tau: '0,80', castiga: 'subestimar', cociente: '4,0×', lectura: 'régimen húmedo', dias: '17,0' },
  { tau: '0,65', castiga: 'subestimar', cociente: '1,9×', lectura: 'umbral de reporte de V⁺', dias: '6,3' },
  { tau: '0,50', castiga: 'ninguno', cociente: '1,0×', lectura: 'acá la función es exactamente el RMSE', dias: '—', mid: true },
  { tau: '0,35', castiga: 'sobrestimar', cociente: '1,9×', lectura: 'umbral de reporte de V⁻', dias: '6,4' },
  { tau: '0,20', castiga: 'sobrestimar', cociente: '4,0×', lectura: 'régimen seco', dias: '17,3' },
  { tau: '0,15', castiga: 'sobrestimar', cociente: '5,7×', lectura: 'estiaje pleno: el optimismo es lo caro', dias: '11,2' },
]

const LIMIT_ROWS = [
  { param: 'τ_max', valor: '0,85', acota: 'Techo de la asimetría: el clip deja τ en [0,15 ; 0,85], castigo máximo 5,7× hacia cualquier lado.', trato: 'Se declara' },
  { param: 'κ', valor: '2,2', acota: 'Nitidez de la S (por qué tanh, más abajo).', trato: 'Sensibilidad' },
  { param: 'γ · w_ant/w_fc', valor: '0,85 · 0,35/0,65', acota: 'Peso por lead (+1 pesa 4,3× el +14) y pasado vs. pronóstico.', trato: 'Sensibilidad' },
  { param: 'ventanas · Q₀', valor: '30 d · 14 d · 100', acota: 'Memoria de humedad del suelo, horizonte máximo del target y piso del logaritmo.', trato: 'Fijo' },
]

const REFERENCES = [
  {
    title: 'River flow forecasting through conceptual models part I — A discussion of principles',
    meta: 'Nash, J. E.; Sutcliffe, J. V. (1970) · Journal of Hydrology 10(3), 282–290 · doi:10.1016/0022-1694(70)90255-6',
    role: 'Origen del NSE. Es una de las métricas que G-RAL acompaña y nunca reemplaza.',
    tag: 'NSE',
  },
  {
    title: 'Decomposition of the mean squared error and NSE performance criteria: Implications for improving hydrological modelling',
    meta: 'Gupta, H. V.; Kling, H.; Yilmaz, K. K.; Martinez, G. F. (2009) · Journal of Hydrology 377(1-2), 80–91 · doi:10.1016/j.jhydrol.2009.08.003',
    role: 'Origen del KGE. Descompone el error cuadrático en correlación, sesgo y variabilidad — la lectura que explica por qué gral mejora KGE aunque empeore RMSE.',
    tag: 'KGE',
  },
  {
    title: 'Technical note: Pitfalls in using log-transformed flows within the KGE criterion',
    meta: 'Santos, L.; Thirel, G.; Perrin, C. (2018) · Hydrology and Earth System Sciences 22, 4583–4591 · doi:10.5194/hess-22-4583-2018',
    role: 'ADVERTENCIA QUE APLICA. El log dentro del KGE produce evaluación sesgada. Este proyecto usa log dentro de un criterio cuadrático (donde sí es el uso clásico) y reporta KGE sobre caudal SIN transformar.',
    tag: 'advertencia',
  },
]

const PENDIENTE = [
  { tag: 'log-NSE', text: 'NSE calculado sobre el logaritmo del caudal en vez del caudal crudo — más sensible a los caudales bajos, donde el NSE estándar casi no penaliza.' },
  { tag: '% error de volumen', text: 'Sesgo de volumen total acumulado (PBIAS-like) sobre una ventana, no error puntual día a día — relevante para operación de embalse.' },
  { tag: 'Kling-Gupta Efficiency', text: 'Descompone el error en correlación, sesgo y variabilidad (Gupta et al. 2009, ver referencias). Ya se reporta KGE sobre caudal crudo; falta evaluarlo como criterio de selección, no sólo de reporte.' },
  { tag: 'Excedencia', text: 'Métrica de probabilidad de excedencia / curva de duración de caudales — qué tan bien el modelo reproduce la frecuencia de caudales altos y bajos, no sólo el valor puntual.' },
  { tag: 'Multi-objetivo', text: 'Optimizar más de un criterio a la vez (p. ej. G-RAL + NSE, o G-RAL + V⁻) en vez de un escalar único con gates posteriores — Pareto en vez de un solo número.' },
]

export function FuncionGananciaPage() {
  return (
    <div className={styles.page}>
      <h1>Función de ganancia</h1>
      <p>
        Qué se optimiza hoy y por qué, con el detalle de <code>docs/referencia_funcion_y_dataset.html</code>{' '}
        (worktree de predicción). Lo marcado <b>«se declara»</b> es criterio, no ajuste.
      </p>

      <Panel title="1 · G-RAL — la función de ganancia">
        <p>
          Un error cuadrático medio con <b>dos cambios</b>: se mide sobre el <b>logaritmo</b> del caudal, y el
          peso de cada error depende de <b>su signo</b> y del <b>día</b>.
        </p>
        <div className={styles.eq}>
{`ε(t,h)  =  ln Q_obs(t+h) − ln Q_pred(t+h)       ε > 0 ⇒ el modelo subestimó
ψ_τ(ε)  =  2 · |τ − 1{ε < 0}| · ε²              pérdida expectil (Newey & Powell, 1987)
G-RAL(h) = √( media_t  ψ_τ(t)( ε(t,h) ) )`}
        </div>
        <p className={styles.eqNote}>
          Con τ = 0,5 y sin logaritmo, <b>G-RAL es el RMSE</b> — dígito por dígito, no una aproximación. Piso del
          logaritmo Q₀ = 100 m³/s, por debajo del p1 observado (204): nunca se activa con datos reales.
        </p>

        <h3>Qué significa τ, y cuánto castiga</h3>
        <p>
          <b>Decisión: τ se lee como un precio.</b> El cociente τ/(1−τ) dice cuántas veces más caro es
          equivocarse para un lado que para el otro. <b>τ no se estima de los datos: se declara</b>, y expresa
          un criterio de operación — discutible con quien opera el embalse, en unidades de costo y no de
          estadística — no un parámetro que el modelo ajuste.
        </p>
        <div className={tableStyles.wrap}>
          <table className={tableStyles.table}>
            <thead>
              <tr>
                <th className={tableStyles.num}>τ</th>
                <th>Castiga más</th>
                <th className={tableStyles.num}>Cociente</th>
                <th>Lectura operativa</th>
                <th className={tableStyles.num}>% días</th>
              </tr>
            </thead>
            <tbody>
              {TAU_ROWS.map((r) => (
                <tr key={r.tau} style={r.mid ? { background: 'var(--code-bg)', fontWeight: 600 } : undefined}>
                  <td className={tableStyles.num}>{r.tau}</td>
                  <td>
                    {r.castiga === 'ninguno' ? (
                      r.castiga
                    ) : (
                      <span style={{ color: r.castiga === 'subestimar' ? '#2647b0' : '#8f5709', fontWeight: 600 }}>
                        {r.castiga}
                      </span>
                    )}
                  </td>
                  <td className={tableStyles.num}>{r.cociente}</td>
                  <td>{r.lectura}</td>
                  <td className={tableStyles.num}>{r.dias}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className={styles.eqNote}>
          % de días sobre 9.628 del snapshot delta 299, modulador en modo oráculo. <b>La función cambia de
          signo:</b> 49 % de los días castiga más subestimar y 51 % más sobrestimar. En estiaje no es más
          indulgente — es exigente al revés.
        </p>
      </Panel>

      <Panel title="2 · Cómo se calcula τ cada día">
        <p>
          Función determinista de la lluvia — misma lluvia, mismo τ, nadie lo fija a mano.
        </p>
        <div className={styles.twoCol}>
          <ol className={styles.steps}>
            <li>
              <b>Humedad antecedente.</b> Lluvia de los <b>30 días previos</b> (sin incluir hoy), a percentil de
              la serie: <code>A(t)</code>.
            </li>
            <li>
              <b>Lluvia por venir.</b> <b>14 días de pronóstico</b>, ponderando cada lead por <code>γᵏ</code>, a
              percentil: <code>F(t)</code>.
            </li>
            <li>
              <b>Una sola señal.</b> <code>W = 0,35·A + 0,65·F</code>. El pronóstico domina porque es el que
              anticipa la crecida; el pasado modula la respuesta del suelo.
            </li>
            <li>
              <b>Forma de S.</b> <code>r = tanh(κ·(2W−1))</code>, en [−1, +1].
            </li>
            <li>
              <b>A precio.</b> <code>τ = clip(0,5 + 0,35·r)</code>.
            </li>
          </ol>
          <div className={styles.invariantBox}>
            <h4>El invariante que no se puede romper</h4>
            <p>
              El modulador <b>sólo lee lo disponible en t₀</b>: lluvia observada y pronosticada. <b>Nunca el
              caudal del día que se quiere predecir.</b> Si lo leyera, el score dejaría de ser propio y
              premiaría al modelo sesgado a crecida justo en los días donde se lo mira.
            </p>
          </div>
        </div>
      </Panel>

      <Panel title="3 · Por qué la tangente hiperbólica">
        <p>
          <code>W(t)</code> entra como percentil: está repartido uniforme en [0, 1], y un mapeo lineal dejaría{' '}
          <b>43 % de los días</b> amontonados cerca de la simetría, donde la métrica no dice nada distinto del
          RMSE. La <code>tanh</code> con κ = 2,2 baja ese amontonamiento a <b>21 %</b>. Es una S monótona que
          hace tres cosas a la vez: <b>separa</b> el centro (pendiente κ &gt; 1 en el origen), <b>satura</b> en
          ±1 — así τ nunca pasa del techo declarado, sea cual sea W — y deja <b>una sola perilla</b> para
          graduar el reparto.
        </p>
      </Panel>

      <Panel title="4 · Los límites">
        <div className={tableStyles.wrap}>
          <table className={tableStyles.table}>
            <thead>
              <tr>
                <th>Parámetro</th>
                <th className={tableStyles.num}>Valor</th>
                <th>Qué acota</th>
                <th>Cómo se trata</th>
              </tr>
            </thead>
            <tbody>
              {LIMIT_ROWS.map((r) => (
                <tr key={r.param}>
                  <td>
                    <code>{r.param}</code>
                  </td>
                  <td className={tableStyles.num}>{r.valor}</td>
                  <td className={tableStyles.wrapCell}>{r.acota}</td>
                  <td>
                    <Badge tone={r.trato === 'Se declara' ? 'good' : r.trato === 'Fijo' ? 'neutral' : 'warning'}>
                      {r.trato}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className={styles.eqNote}>
          <b>Métricas que la acompañan, siempre:</b> V⁺ = P(subestima | τ &gt; 0,65) · V⁻ = P(sobrestima | τ
          &lt; 0,35) · FA = P(sobrestima | τ &gt; 0,65), más RMSE, NSE y KGE. <b>Criterio de campeón:</b>{' '}
          minimizar G-RAL sujeto a que V⁺ y V⁻ no empeoren contra persistencia.
        </p>
      </Panel>

      <Panel title="5 · NSE — Nash-Sutcliffe Efficiency">
        <p>
          Métrica clásica de calibración hidrológica: compara el error del modelo contra el error de predecir
          siempre la <b>media observada</b>.
        </p>
        <div className={styles.eq}>{`NSE = 1  −  Σ(Q_obs − Q_pred)²  /  Σ(Q_obs − mean(Q_obs))²`}</div>
        <p>
          <b>1</b> = predicción perfecta · <b>0</b> = tan bueno como predecir la media histórica todos los días
          · <b>negativo</b> = peor que esa media. A diferencia de G-RAL, NSE es <b>simétrico</b> (no distingue
          sobre de subestimar) y está dominado por los caudales más altos, porque el error se eleva al cuadrado
          sobre la varianza total — es sensible a la <b>varianza</b>, no al <b>régimen</b>.
        </p>
        <p>
          Por eso en este proyecto se reportan las dos juntas, no una en vez de la otra: G-RAL mide lo que el
          criterio operativo declarado dice que importa (el costo asimétrico por régimen), y NSE mide la
          bondad de ajuste clásica con la que se compara la literatura hidrológica. Pueden divergir — un modelo
          puede mejorar G-RAL sin mejorar NSE en el mismo horizonte, porque están pesando el error de forma
          distinta.
        </p>

        <h3>Referencias</h3>
        <ul className={styles.refList}>
          {REFERENCES.map((r) => (
            <li key={r.title} className={styles.refItem}>
              <div className={styles.refTitle}>
                {r.title} <Badge tone={r.tag === 'advertencia' ? 'warning' : 'neutral'}>{r.tag}</Badge>
              </div>
              <div className={styles.refMeta}>{r.meta}</div>
              <div className={styles.refRole}>{r.role}</div>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel title="Pendiente investigar">
        <ul className={styles.pendienteList}>
          {PENDIENTE.map((p) => (
            <li key={p.tag}>
              <span className={styles.pendienteTag}>
                <Badge tone="neutral">{p.tag}</Badge>
              </span>
              <span>{p.text}</span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  )
}
