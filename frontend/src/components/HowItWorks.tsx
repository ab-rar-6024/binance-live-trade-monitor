import { SystemInfo } from "../api";
import { compact, seconds } from "../format";

function Step({ n, title, plain, tech, live, ok }: { n: number; title: string; plain: string; tech: string; live: string; ok: boolean }) {
  return (
    <li className="step">
      <span className={`step-no ${ok ? "ok" : "bad"}`}>{n}</span>
      <div>
        <div className="strong">{title}</div>
        <p>{plain}</p>
        <p className="muted small">Technical name: {tech}</p>
        <p className="live-line"><span className={`dot ${ok ? "ok" : "bad"}`} /> {live}</p>
      </div>
    </li>
  );
}

/** For the curious: the behind-the-scenes story, with live numbers. Collapsed by default. */
export function HowItWorks({ system }: { system: SystemInfo | undefined }) {
  const topics = system?.kafka.topics ?? {};
  const aggregates = system?.spark.queries["aggregates"];
  const feed = system?.binance_feed;
  const delay = system?.latency_ms.producer_to_spark_p50;

  return (
    <section className="card">
      <details className="how" open>
        <summary>
          <h2>How does this page work? (for the curious)</h2>
          <p className="subtitle">A 30-second tour of what happens between a trade on Binance and the numbers on your screen.</p>
        </summary>

        <ol className="steps">
          <Step
            n={1}
            title="Binance announces every trade"
            plain="Binance is a large exchange where people buy and sell coins. It shares each trade publicly the moment it happens. No account or payment is needed to listen."
            tech="Binance public WebSocket"
            live={feed ? `${feed.trades_per_second.toFixed(0)} trades per second right now` : "connecting…"}
            ok={feed?.status === "live"}
          />
          <Step
            n={2}
            title="A conveyor belt carries them"
            plain="A small program drops each trade onto a conveyor belt that never loses anything. If a later step slows down or restarts, the trades simply wait their turn."
            tech="Apache Kafka"
            live={`${compact(topics["trades.raw"]?.messages)} trades carried so far`}
            ok={!!system?.kafka.connected}
          />
          <Step
            n={3}
            title="An analyst adds everything up"
            plain="Every few seconds an analyst takes the new trades, totals them per coin per minute, and checks each one against what is normal for that coin to spot unusual moments."
            tech="Apache Spark Structured Streaming"
            live={aggregates ? `${aggregates.batch} batches done, about ${(aggregates.proc_rps ?? 0).toFixed(0)} trades analysed per second` : "not running"}
            ok={!!system?.spark.alive}
          />
          <Step
            n={4}
            title="You see the result"
            plain="The results go back on the belt, a Python server picks them up and pushes them to this page, which redraws itself every second."
            tech="FastAPI and React"
            live={delay ? `About ${seconds(delay)} from a trade happening to it being analysed` : "measuring…"}
            ok={!!system}
          />
        </ol>
      </details>
    </section>
  );
}
