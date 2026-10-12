import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Methodology | Q-Flow",
  description: "How Q-Flow models crowd routing, how QAOA works, how results are measured, and the limits of the study.",
};

const SECTIONS = [
  { id: "question", label: "Research question" },
  { id: "model", label: "The model" },
  { id: "score", label: "The score" },
  { id: "classical", label: "Classical solvers" },
  { id: "qaoa", label: "How QAOA works" },
  { id: "modes", label: "Quantum execution modes" },
  { id: "measures", label: "How results are measured" },
  { id: "results", label: "Hardware results" },
  { id: "limitations", label: "Limitations" },
  { id: "tools", label: "Tools" },
];

/** Recorded on 9 October 2026, ibm_fez, QAOA depth 2, 4,096 shots, one run per size. */
const HARDWARE = [
  { qubits: 4, venue: "Micro Hall", ideal: 66, noisy: 56, hw: 62, best: 24.9, random: 6.3, valid: 88.9, gates: "25" },
  { qubits: 6, venue: "Small Event Hall", ideal: 73, noisy: 54, hw: 57, best: 9.4, random: 1.6, valid: 76.2, gates: "69" },
  { qubits: 8, venue: "Concert Venue", ideal: 63, noisy: 42, hw: 46, best: 4.7, random: 0.4, valid: 72.2, gates: "not recorded" },
  { qubits: 10, venue: "Exhibition Centre", ideal: 61, noisy: 32, hw: 23, best: 1.4, random: 0.1, valid: 38.9, gates: "211" },
];

function H2({ id, children }: { id: string; children: React.ReactNode }) {
  return <h2 id={id} className="scroll-mt-6 border-t-2 border-ink pt-3 font-display text-2xl font-bold">{children}</h2>;
}

function Formula({ children }: { children: React.ReactNode }) {
  return (
    <pre className="overflow-x-auto rounded-[3px] border border-line bg-white px-4 py-3 font-mono text-[13px] leading-relaxed">
      {children}
    </pre>
  );
}

export default function MethodologyPage() {
  return (
    <main className="mx-auto max-w-[1440px] px-5 pb-20 pt-10">
      <h1 className="max-w-[22ch] font-display text-[clamp(2rem,4.5vw,3.4rem)] font-bold leading-[1.05]">
        Methodology, QAOA and limitations
      </h1>
      <p className="mt-3 max-w-[70ch] text-ink-soft">
        How Q-Flow turns crowd routing into an optimisation problem, how each solver attacks it, how the results are
        measured, and what the study can and cannot show.
      </p>

      <div className="mt-10 grid items-start gap-10 lg:grid-cols-[220px_minmax(0,1fr)]">
        <nav aria-label="On this page" className="lg:sticky lg:top-6">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-soft">On this page</p>
          <ol className="space-y-1.5 text-sm">
            {SECTIONS.map((s) => (
              <li key={s.id}><a href={`#${s.id}`} className="text-ink-soft hover:text-ink">{s.label}</a></li>
            ))}
          </ol>
        </nav>

        <article className="min-w-0 max-w-[1100px] space-y-12 leading-relaxed [&_h2]:max-w-[78ch] [&_li]:max-w-[78ch] [&_p]:max-w-[78ch] [&_pre]:max-w-[78ch]">
          {/* ------------------------------------------------------------ question */}
          <section className="space-y-3">
            <H2 id="question">Research question</H2>
            <p>
              <b>To what extent can current quantum optimisation techniques provide useful solutions to simplified
              crowd flow planning problems, compared with classical optimisation?</b>
            </p>
            <p>
              Q-Flow does not set out to show quantum computing winning. Classical methods are expected to stay well
              ahead on problems of this size. The aim is to measure the gap, and to see how it changes with problem
              size, circuit depth and hardware noise. A result where classical methods clearly win is still a valid and
              useful result.
            </p>
          </section>

          {/* --------------------------------------------------------------- model */}
          <section className="space-y-3">
            <H2 id="model">The model</H2>
            <p>
              A venue is a <b>graph</b>. Places (entrances, halls, corridors, seating, exits) are nodes, and routes
              between them are edges. Each route has a capacity and a length, and optionally a travel time. Each exit
              has a capacity. Crowd groups start at a place and must leave through an exit.
            </p>
            <p>
              For each group, Q-Flow finds a small set of <b>candidate routes</b> to the exits. The shortest route to
              each exit comes from Dijkstra&apos;s algorithm, and further alternatives come from Yen&apos;s algorithm,
              which lists the next shortest paths. The number of candidates per group is set by &quot;Routes considered
              per group&quot; in the Lab.
            </p>
            <p>
              Each pair of group and candidate route is one <b>binary decision</b>: 1 if the group takes that route, 0
              if not. Each decision becomes one qubit, so a venue with 5 groups and 2 routes each needs 10 qubits. A
              valid plan sends every group down exactly one route.
            </p>
          </section>

          {/* --------------------------------------------------------------- score */}
          <section className="space-y-3">
            <H2 id="score">The score</H2>
            <p>
              Every plan receives one score, and every solver tries to make it as low as possible. The score is
              written as a QUBO (Quadratic Unconstrained Binary Optimisation): a sum of terms on single decisions and
              on pairs of decisions.
            </p>
            <Formula>{`score = w_distance × Distance + w_time × Time
      + w_congestion × Congestion + w_overflow × Overflow
      + A × (one route per group penalty)`}</Formula>
            <ul className="list-disc space-y-2 pl-5">
              <li><b>Distance:</b> people multiplied by metres walked, normalised.</li>
              <li><b>Time:</b> people multiplied by travel time. Where a route has no travel time, it is estimated from its length at 1.3 m/s, so time then behaves like distance.</li>
              <li><b>Congestion:</b> for every route and exit, (load ÷ capacity)², averaged. It rises sharply as a route fills, so it spreads people out.</li>
              <li><b>Overflow:</b> people above capacity. The true rule, max(0, load − capacity), cannot be written exactly as a QUBO, so Q-Flow fits the closest quadratic approximation. It is exact when two or fewer groups share a route or exit.</li>
              <li><b>Penalty A:</b> added for every group that takes no route or more than one. A is set from the cost of the simple nearest exit plan, so any invalid plan always scores worse than the best valid one.</li>
            </ul>
            <p>
              The weights are the sliders under &quot;Optimisation priorities&quot;. For quantum hardware the QUBO is
              converted into an <b>Ising Hamiltonian</b>, which is the same score written in terms of qubit spins (+1
              and −1 instead of 0 and 1). This is the form a quantum circuit can work with directly.
            </p>
          </section>

          {/* ----------------------------------------------------------- classical */}
          <section className="space-y-3">
            <H2 id="classical">Classical solvers</H2>
            <p>All classical solvers use exactly the same score as QAOA, so the comparison is fair.</p>
            <ul className="list-disc space-y-2 pl-5">
              <li>
                <b>Exhaustive search</b> (the Lab&apos;s &quot;Classical&quot; option). It lists every valid plan, scores
                each one with NumPy, and keeps the lowest. The answer is guaranteed to be the best plan for the score.
                It is the reference that every quantum result is measured against. It is limited to 2 million valid plans.
              </li>
              <li>
                <b>Google OR-Tools CP-SAT</b>, for venues too large to list every plan. It is a constraint solver that
                searches cleverly rather than exhaustively, with a 10 second limit. Its plan is re-scored with the same
                formula so its numbers are exact.
              </li>
              <li>
                <b>Nearest exit</b>, the &quot;before&quot; plan. Each group takes its shortest route and capacity is
                ignored. It shows what happens without optimisation.
              </li>
            </ul>
          </section>

          {/* ---------------------------------------------------------------- qaoa */}
          <section className="space-y-3">
            <H2 id="qaoa">How QAOA works</H2>
            <p>
              The Quantum Approximate Optimisation Algorithm searches for low scoring plans by shaping the odds of
              what a quantum computer measures.
            </p>
            <ol className="list-decimal space-y-2 pl-5">
              <li><b>Start with every plan at once.</b> A Hadamard gate on every qubit puts the register into an equal mix of all possible bit strings, so every plan, valid or not, is equally likely.</li>
              <li><b>Cost layer.</b> Gates built from the score (RZ on single qubits, RZZ on pairs) give each plan a phase that depends on its score. The strength of this step is an angle called gamma.</li>
              <li><b>Mixer layer.</b> An RX gate on every qubit lets the plans interfere, so that phases turn into changes in probability. Its strength is an angle called beta.</li>
              <li><b>Repeat.</b> One cost layer plus one mixer layer is one depth step, called p. More layers can fit the problem better, but each one adds gates, and gates add errors.</li>
              <li><b>Measure.</b> Measuring the qubits gives one bit string, which is one plan. Repeating this thousands of times (shots) gives a spread of plans, ideally weighted towards good ones.</li>
            </ol>
            <p>
              <b>Training the angles.</b> The angles are chosen on a classical computer by simulating the circuit
              exactly and minimising the average score. For p = 1, a 16 × 16 grid search is followed by the COBYLA
              optimiser. For deeper circuits, each depth starts from the previous best angles stretched to the new
              depth (the INTERP method of Zhou et al., 2020), which avoids unreliable random restarts. The trained
              angles are then reused unchanged on the noisy simulator and on real hardware, which is how QAOA is
              normally run on today&apos;s devices.
            </p>
            <p>
              QAOA is <b>approximate</b>. It makes good plans more likely, but it does not guarantee the best one, and
              most shots usually return a weaker plan. That is why Q-Flow reports how often the best plan appears and
              how good a typical shot is, not just the single best shot.
            </p>
          </section>

          {/* --------------------------------------------------------------- modes */}
          <section className="space-y-3">
            <H2 id="modes">Quantum execution modes</H2>
            <ul className="list-disc space-y-2 pl-5">
              <li><b>Ideal simulator.</b> Qiskit Aer with no errors. This is what QAOA could do on a perfect quantum computer.</li>
              <li>
                <b>Noisy simulator.</b> The same circuit with errors added. Two noise models are available. The
                adjustable error rate model applies gate and readout errors at a chosen level (1x is about 0.1% per
                single qubit gate, 1% per two qubit gate and 2% per readout), with every qubit connected to every
                other. The real device model uses the calibration data and qubit layout of an IBM processor, which
                also adds the extra swap gates a real chip needs.
              </li>
              <li>
                <b>IBM quantum hardware.</b> The circuit is adapted to a real IBM processor (Qiskit transpiler,
                optimisation level 1) and sent through Qiskit IBM Runtime. Jobs wait in IBM&apos;s queue and use the
                account&apos;s processor time allowance. A free &quot;Check circuit&quot; step shows the adapted
                circuit&apos;s size before anything is sent.
              </li>
            </ul>
          </section>

          {/* ------------------------------------------------------------ measures */}
          <section className="space-y-3">
            <H2 id="measures">How results are measured</H2>
            <ul className="list-disc space-y-2 pl-5">
              <li>
                <b>Typical answer quality</b> (the approximation ratio). For one plan:
                <Formula>{`quality = (worst valid score − plan score)
        ÷ (worst valid score − best score)`}</Formula>
                The best plan scores 100% and the worst valid plan 0%. Invalid plans count as 0%. For quantum solvers
                this is averaged over every shot, so it describes what a single run usually gives.
              </li>
              <li><b>Chance of the best plan:</b> the share of shots that return the best plan, shown next to the chance from random guessing.</li>
              <li><b>Valid plans:</b> the share of shots where every group takes exactly one route. Noise lowers this first.</li>
              <li><b>People over capacity:</b> the exact number of people who would have to be removed for every route and exit to fit, calculated with a linear programme (SciPy). It is not part of the score, so it checks the score honestly.</li>
              <li><b>Best of all shots:</b> the single best plan seen in any shot. On small problems even random guessing finds the best plan within a few thousand shots, so this measure flatters quantum and is never used on its own.</li>
            </ul>
          </section>

          {/* ------------------------------------------------------------- results */}
          <section className="space-y-3">
            <H2 id="results">Hardware results</H2>
            <p className="text-sm text-ink-soft">
              Recorded on 9 October 2026 on ibm_fez, QAOA depth 2, 4,096 shots, one run per size. Single runs vary,
              so these figures are a snapshot, not averages. Typical answer quality is shown for each mode.
            </p>
            <div className="overflow-x-auto rounded-[4px] border border-line bg-panel">
              <table className="w-full min-w-[720px] border-collapse text-sm">
                <thead>
                  <tr className="border-b border-line text-left">
                    <th className="px-4 py-2 font-medium text-ink-soft">Qubits</th>
                    <th className="px-4 py-2 font-medium text-ink-soft">Venue</th>
                    <th className="px-4 py-2 text-right font-semibold text-quantum">Ideal</th>
                    <th className="px-4 py-2 text-right font-semibold text-quantum">Noisy (1x)</th>
                    <th className="px-4 py-2 text-right font-semibold text-quantum">IBM hardware</th>
                    <th className="px-4 py-2 text-right font-medium text-ink-soft">Best plan (hardware)</th>
                    <th className="px-4 py-2 text-right font-medium text-ink-soft">Random guess</th>
                    <th className="px-4 py-2 text-right font-medium text-ink-soft">Valid (hardware)</th>
                    <th className="px-4 py-2 text-right font-medium text-ink-soft">Two qubit gates</th>
                  </tr>
                </thead>
                <tbody>
                  {HARDWARE.map((r) => (
                    <tr key={r.qubits} className="num border-b border-line/70 last:border-0">
                      <td className="px-4 py-2 font-semibold">{r.qubits}</td>
                      <td className="whitespace-nowrap px-4 py-2">{r.venue}</td>
                      <td className="px-4 py-2 text-right">{r.ideal}%</td>
                      <td className="px-4 py-2 text-right">{r.noisy}%</td>
                      <td className="px-4 py-2 text-right font-bold">{r.hw}%</td>
                      <td className="px-4 py-2 text-right">{r.best}%</td>
                      <td className="px-4 py-2 text-right text-ink-soft">{r.random}%</td>
                      <td className="px-4 py-2 text-right">{r.valid}%</td>
                      <td className="px-4 py-2 text-right">{r.gates}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul className="list-disc space-y-2 pl-5">
              <li><b>Quality falls as problems grow.</b> On hardware, typical quality drops from 62% at 4 qubits to 23% at 10.</li>
              <li><b>Gate count drives the drop.</b> Two qubit gates rise from 25 to 211 once the circuit is fitted to the chip, and by 10 qubits only 39% of shots are valid plans.</li>
              <li><b>The simple noise model is only a guide.</b> The real device did better than the 1x model at 4 qubits and worse at 10.</li>
              <li><b>QAOA still beats random guessing at every size,</b> but at 10 qubits a typical hardware answer is worse than the simple nearest exit plan.</li>
            </ul>
          </section>

          {/* --------------------------------------------------------- limitations */}
          <section className="space-y-3">
            <H2 id="limitations">Limitations</H2>
            <h3 className="font-display text-lg font-bold">The model</h3>
            <ul className="list-disc space-y-2 pl-5">
              <li><b>It is a routing plan, not a crowd simulation.</b> There is no movement over time, no walking speed differences and no behaviour. The map shows the result of the plan, not people moving.</li>
              <li><b>Each group moves as one block</b> down one route. A large group cannot be split between routes unless it is entered as several groups.</li>
              <li><b>Only routes and exits have capacities.</b> Rooms and corridors themselves do not.</li>
              <li><b>Capacity is a penalty, not a hard rule.</b> The overflow term is an approximation, so a plan can still overload a route when the other parts of the score outweigh it. The exact people over capacity figure is always shown so this cannot go unnoticed.</li>
              <li><b>Only the candidate routes are considered.</b> The best plan is the best among those routes. More routes per group can find better plans but need more qubits.</li>
              <li><b>The time priority equals distance</b> unless travel times are entered on routes.</li>
              <li><b>The congestion score in the comparison table includes its weight,</b> so it should only be compared between runs with the same priorities.</li>
            </ul>
            <h3 className="font-display text-lg font-bold">The quantum side</h3>
            <ul className="list-disc space-y-2 pl-5">
              <li><b>Small problems only.</b> Simulation is limited to 16 qubits, and real hardware results are close to unusable beyond about 10.</li>
              <li><b>Angles are trained in simulation</b> and reused on noisy runs and hardware, not retrained on the device.</li>
              <li><b>The adjustable noise model is simplified,</b> with uniform errors and every qubit connected to every other.</li>
              <li><b>Hardware results vary</b> between runs and between days, as device calibration changes. Runs also depend on queue time and the account&apos;s processor time allowance.</li>
              <li><b>No quantum advantage is claimed.</b> The exhaustive classical search solved every venue tested here in under a millisecond.</li>
            </ul>
          </section>

          {/* --------------------------------------------------------------- tools */}
          <section className="space-y-3">
            <H2 id="tools">Tools</H2>
            <ul className="list-disc space-y-2 pl-5">
              <li><b>Quantum:</b> Qiskit (circuits and transpiler), Qiskit Aer (ideal and noisy simulation), Qiskit IBM Runtime (real hardware), Qiskit Optimization (exporting the problem in Qiskit&apos;s standard QuadraticProgram format).</li>
              <li><b>Classical:</b> NetworkX (venue graph and candidate routes), NumPy (exhaustive search and the overflow fit), SciPy (COBYLA angle training and the exact capacity check), Google OR-Tools CP-SAT (larger venues).</li>
              <li><b>Application:</b> FastAPI backend, Next.js, React and TypeScript frontend, React Flow venue editor, Recharts charts, SQLite storage.</li>
            </ul>
          </section>
        </article>
      </div>
    </main>
  );
}
