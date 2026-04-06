import React, { useEffect, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from "recharts";

export default function Dashboard() {
  const [data, setData] = useState([]);
  const [selectedMetric, setSelectedMetric] = useState("response");

  // 🔹 Fetch data
  useEffect(() => {
    fetch("/results.json")
      .then(res => res.json())
      .then(data => {
        console.log(data); 
        setData(data);
      });
  }, []);

  // 🔹 Button style function
  const getButtonStyle = (metric) => ({
    padding: "10px 15px",
    borderRadius: "8px",
    border: "none",
    cursor: "pointer",
    background: selectedMetric === metric ? "#007bff" : "#ddd",
    color: selectedMetric === metric ? "white" : "black",
    fontWeight: "bold"
  });

  return (
    <div style={{ padding: "20px", fontFamily: "Arial" }}>

      {/* TITLE */}
      <h1 style={{ textAlign: "center" }}>
        Adaptive SDN-Based Load Balancing Dashboard
      </h1>

      {/* BUTTONS */}
      <div style={{
        display: "flex",
        justifyContent: "center",
        gap: "10px",
        marginBottom: "20px",
        flexWrap: "wrap"
      }}>
        <button style={getButtonStyle("response")} onClick={() => setSelectedMetric("response")}>
          Response Time
        </button>

        <button style={getButtonStyle("throughput")} onClick={() => setSelectedMetric("throughput")}>
          Throughput
        </button>

        <button style={getButtonStyle("makespan")} onClick={() => setSelectedMetric("makespan")}>
          Makespan
        </button>

        <button style={getButtonStyle("delay")} onClick={() => setSelectedMetric("delay")}>
          Delay
        </button>

        <button style={getButtonStyle("utilization")} onClick={() => setSelectedMetric("utilization")}>
          Utilization
        </button>
      </div>

      {/* 🔷 TITLE BASED ON SELECTION */}
      <h2 style={{ textAlign: "center", marginBottom: "20px" }}>
        {selectedMetric.toUpperCase()} ANALYSIS
      </h2>

      {/* 🔷 GRAPH */}
      <ResponsiveContainer width="100%" height={400}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="tasks" />
          <YAxis />
          <Tooltip />
          <Legend />

          {/* RESPONSE */}
          {selectedMetric === "response" && (
            <>
              <Line dataKey="rr" stroke="red" name="Round Robin" />
              <Line dataKey="proposed" stroke="green" name="Proposed" />
            </>
          )}

          {/* THROUGHPUT */}
          {selectedMetric === "throughput" && (
            <>
              <Line dataKey="rr_throughput" stroke="red" name="Round Robin" />
              <Line dataKey="proposed_throughput" stroke="green" name="Proposed" />
            </>
          )}

          {/* MAKESPAN */}
          {selectedMetric === "makespan" && (
            <>
              <Line dataKey="rr_makespan" stroke="red" name="Round Robin" />
              <Line dataKey="proposed_makespan" stroke="green" name="Proposed" />
            </>
          )}

          {/* DELAY */}
          {selectedMetric === "delay" && (
            <>
              <Line dataKey="rr_delay" stroke="red" name="Round Robin" />
              <Line dataKey="proposed_delay" stroke="green" name="Proposed" />
            </>
          )}

          {/* UTILIZATION */}
          {selectedMetric === "utilization" && (
            <>
              <Line dataKey="rr_utilization" stroke="red" name="Round Robin" />
              <Line dataKey="proposed_utilization" stroke="green" name="Proposed" />
            </>
          )}

        </LineChart>
      </ResponsiveContainer>

    </div>
  );
}