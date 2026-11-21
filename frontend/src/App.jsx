import { useEffect, useState } from "react";

// Lists the geometries in the database, from the FastAPI endpoint in
// src/autostorage/gui/app.py (API docs: http://127.0.0.1:8765/docs)
export default function App() {
  const [geometries, setGeometries] = useState([]);

  useEffect(() => {
    fetch("/api/geometries")
      .then((response) => response.json())
      .then(setGeometries);
  }, []);

  return (
    <main className="mx-auto max-w-xl p-8">
      <h1 className="mb-4 text-2xl font-semibold">AutoStorage</h1>
      <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200">
        {geometries.map((geo) => (
          <li key={geo.id} className="px-4 py-2">
            {geo.formula}
            <span className="ml-2 text-sm text-slate-500">{geo.natoms} atoms</span>
          </li>
        ))}
      </ul>
    </main>
  );
}
