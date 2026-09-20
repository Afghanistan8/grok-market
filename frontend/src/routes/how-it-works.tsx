import { env } from "../lib/env";

function Rule({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="panel p-6">
      <h2 className="text-base text-zinc-100">{title}</h2>
      <div className="mt-3 space-y-3 text-sm leading-relaxed text-zinc-400">{children}</div>
    </div>
  );
}

export function HowItWorksPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="mb-8">
        <h1 className="text-3xl text-zinc-50">How settlement works</h1>
        <p className="mt-2 text-zinc-500">
          The rules in plain language. Nothing here is a simplification of something stricter
          happening elsewhere — this is the whole mechanism.
        </p>
      </div>

      <Rule title="There is no admin">
        <p>
          The contract has no owner, no pause switch, no admin resolve and no upgrade hook. It
          stores no privileged address of any kind. Nobody — including whoever deployed it — can
          change an outcome, freeze a market or take a stake.
        </p>
      </Rule>

      <Rule title="There is no single oracle">
        <p>
          Nothing writes a price on chain for the contract to read. When a market settles, the
          contract itself makes the HTTP requests, from inside a GenLayer equivalence-principle
          block, and parses the responses.
        </p>
        <p>
          Every asset has <strong className="text-zinc-200">two independent sources</strong>.
          Crypto settles on CoinGecko and Binance; stocks settle on stockanalysis.com and Nasdaq.
        </p>
      </Rule>

      <Rule title="Each source is read on its own">
        <p>
          The contract reconstructs the target GMT+1 day from each source separately, using only
          that source's own numbers, and derives a verdict from each one independently. The two
          reads never see each other.
        </p>
        <p>
          For a direction market the verdict is up or down. For a relative-return market it is
          whichever asset posted the largest percentage move that day.
        </p>
      </Rule>

      <Rule title="Both sources must agree">
        <p>
          A market only settles when both sources independently produce the{" "}
          <strong className="text-zinc-200">same</strong> verdict. The winning side then splits the
          entire pool in proportion to stake.
        </p>
        <p>
          A single source can never produce a result. There is no code path where one feed's
          answer becomes the outcome.
        </p>
      </Rule>

      <Rule title="Disagreement refunds everyone">
        <p>
          If the two sources reach different verdicts, the market settles inconclusive and{" "}
          <strong className="text-zinc-200">every staker withdraws exactly what they put in</strong>
          . Nobody wins and nobody loses.
        </p>
        <p>
          This happens most often on near-flat days, where a cross-exchange average and a single
          venue's pair can genuinely differ on the sign of a tiny move. That is the honest answer:
          the day had no clear direction, so the contract refuses to invent one.
        </p>
        <p>
          In a relative-return market, a tie for first place on <em>either</em> source also refunds
          everyone — a tie cannot produce a winner.
        </p>
      </Rule>

      <Rule title="Unavailable data just means retry">
        <p>
          If a source times out, rate limits, or returns something the contract cannot parse, the
          whole transaction reverts and nothing is written. The market stays resolvable and anyone
          can try again later.
        </p>
        <p>
          The same applies when a market was closed that day: a weekend or holiday has no session,
          so neither stock feed has a row, and the contract declines to settle rather than
          inventing an overnight print.
        </p>
      </Rule>

      <Rule title="After five days, everyone gets their stake back">
        <p>
          Five days after the day closes, resolution switches to a terminal refund. At that point
          the contract{" "}
          <strong className="text-zinc-200">stops asking the web anything at all</strong>, marks
          the market inconclusive and lets everyone withdraw their original stake.
        </p>
        <p>
          It never fabricates a price, a direction or a winner to close a market out. This path has
          no external dependency, so it cannot itself fail — your stake cannot be locked forever by
          a feed that disappeared.
        </p>
      </Rule>

      <Rule title="The prices on this site do not settle anything">
        <p>
          The chart on a market page is decoration. It is fetched by your browser, from a different
          path, purely so there is something to look at.
        </p>
        <p>
          Settlement happens entirely inside the contract, against the origin APIs, under
          consensus. If the chart here disagreed with the outcome, the chart is the thing that is
          wrong.
        </p>
      </Rule>

      <Rule title="Stakes are 2 to 6 GEN">
        <p>
          A first position must be at least 2 GEN, and your total on any one market can never
          exceed 6 GEN. You can top up the side you already hold. You cannot switch sides — pick
          deliberately.
        </p>
        <p>Positions close the moment the GMT+1 day begins.</p>
      </Rule>

      <Rule title="Anyone can resolve a market">
        <p>
          Once the day is complete, resolution is open to any wallet. There is no keeper and no
          bot you have to rely on. Whoever wants the outcome recorded pays the gas to record it.
        </p>
      </Rule>

      <Rule title="Point your wallet at the GenLayer RPC">
        <p>
          Use <code className="rounded bg-black/40 px-1 text-zinc-300">{env.defaultRpc}</code> for
          chain 4221.
        </p>
        <p>
          ChainList also lists a zkSync-OS host for this chain. That one rate limits transactions
          and answers{" "}
          <code className="rounded bg-black/40 px-1 text-zinc-300">-32005 gas rate limit</code>, so
          your transactions will simply never land. If your wallet already saved it, open MetaMask
          → Settings → Networks → GenLayer and replace the RPC URL.
        </p>
      </Rule>

      <div className="panel p-6">
        <h2 className="text-base text-zinc-100">Want the exact rules?</h2>
        <p className="mt-3 text-sm text-zinc-400">
          <code className="text-zinc-300">docs/RESOLUTION.md</code> in the repository has the
          precise URL templates, how open and close are chosen from each feed, the basis-point
          ranking, the stock session rules, and the eight checks the contract runs on the agreed
          payload before it writes anything.
        </p>
      </div>
    </div>
  );
}
