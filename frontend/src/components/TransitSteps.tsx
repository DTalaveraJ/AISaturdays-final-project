"use client";

interface TransitStep {
  mode: string;
  instruction: string;
  duration: string;
  distance?: string;
  line_name?: string;
  vehicle_type?: string;
  departure_stop?: string;
  arrival_stop?: string;
  num_stops?: number;
}

interface Props {
  steps: TransitStep[];
}

const VEHICLE_ICON: Record<string, string> = {
  Subway: "🚇",
  Metro: "🚇",
  Bus: "🚌",
  Tram: "🚊",
  Train: "🚆",
  Ferry: "⛴️",
  "Cable car": "🚡",
};

function vehicleIcon(type: string): string {
  for (const [key, icon] of Object.entries(VEHICLE_ICON)) {
    if (type.toLowerCase().includes(key.toLowerCase())) return icon;
  }
  return "🚌";
}

export function TransitSteps({ steps }: Props) {
  if (!steps || steps.length === 0) return null;

  return (
    <div className="bg-[#1a3646] rounded-lg border border-[#2c6675] p-4 mt-4">
      <h3 className="font-semibold text-sm text-gray-100 mb-3">
        🚌 Indicaciones de transporte público
      </h3>
      <ol className="space-y-2">
        {steps.map((step, idx) => (
          <li key={idx} className="flex gap-3 items-start text-sm">
            {/* Icon column */}
            <span className="mt-0.5 text-base shrink-0">
              {step.mode === "WALKING" ? "🚶" : vehicleIcon(step.vehicle_type || "")}
            </span>

            {/* Content */}
            <div className="flex-1 min-w-0">
              {step.mode === "TRANSIT" && step.line_name ? (
                <>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="bg-green-700 text-white text-xs font-bold px-2 py-0.5 rounded">
                      {step.line_name}
                    </span>
                    {step.vehicle_type && (
                      <span className="text-gray-400 text-xs">{step.vehicle_type}</span>
                    )}
                    <span className="text-gray-400 text-xs">{step.duration}</span>
                    {step.num_stops ? (
                      <span className="text-gray-500 text-xs">({step.num_stops} paradas)</span>
                    ) : null}
                  </div>
                  {step.departure_stop && step.arrival_stop && (
                    <div className="text-gray-300 mt-0.5">
                      <span className="text-[#8ec3b9]">{step.departure_stop}</span>
                      <span className="text-gray-500 mx-1">→</span>
                      <span className="text-[#8ec3b9]">{step.arrival_stop}</span>
                    </div>
                  )}
                </>
              ) : (
                <div className="text-gray-300">
                  {step.instruction}
                  <span className="text-gray-500 ml-2 text-xs">
                    {step.duration}{step.distance ? ` · ${step.distance}` : ""}
                  </span>
                </div>
              )}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
