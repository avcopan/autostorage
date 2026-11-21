import { useEffect, useState } from "react";

export default function App() {
  const [message, setMessage] = useState("Loading…");

  useEffect(() => {
    fetch("/api/hello")
      .then((response) => response.json())
      .then((data) => setMessage(data.message));
  }, []);

  return <h1 className="p-8 text-3xl font-bold">{message}</h1>;
}
