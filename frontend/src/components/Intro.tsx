import { useState } from "react";

const KEY = "intro-dismissed";

function wasDismissed(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false; // storage can be blocked; just show the guide
  }
}

/** A short "how to read this page" guide for first-time visitors. */
export function Intro() {
  const [hidden, setHidden] = useState(wasDismissed);

  const hide = (value: boolean) => {
    setHidden(value);
    try {
      localStorage.setItem(KEY, value ? "1" : "0");
    } catch {
      /* ignore */
    }
  };

  if (hidden) {
    return (
      <button className="link-button" onClick={() => hide(false)}>
        ? How to read this page
      </button>
    );
  }

  return (
    <section className="card intro">
      <div className="intro-head">
        <h2>New here? Start with these 4 ideas</h2>
        <button className="link-button" onClick={() => hide(true)}>Got it, hide this</button>
      </div>
      <ol className="intro-steps">
        <li>
          <b>Coins are digital money.</b> Bitcoin, Ethereum and others are bought and sold all day on an exchange called Binance.
          Every sale is a <b>trade</b>.
        </li>
        <li>
          <b>Prices are in dollars.</b> We show prices in USDT, a coin that is worth about one US dollar, so $100 here means about $100.
        </li>
        <li>
          <b>This page watches every trade as it happens</b> and sums them up: what each coin costs, who is buying or selling, and
          which coins are busiest.
        </li>
        <li>
          <b>It also flags unusual moments</b>, like one very large trade or a sudden price jump, so you don't have to stare at numbers.
        </li>
      </ol>
      <p className="note">This page only shows what is happening. It does not predict prices and is not financial advice.</p>
    </section>
  );
}
