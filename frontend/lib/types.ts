export type HealthResponse = {
  status: string;
  service: string;
};

export type DriverSeries = "F1" | "F2" | "Reserve" | "Other";
export type TeamSeries = "F1" | "F2";

export type DriverAttributes = {
  pace: number;
  qualifying: number;
  racecraft: number;
  tireManagement: number;
  wetWeather: number;
  consistency: number;
  starts: number;
  awareness: number;
  adaptability: number;
  technicalFeedback: number;
  pressure: number;
  confidence: number;
  composure: number;
  aggression: number;
  discipline: number;
  focus: number;
  reputation: number;
  marketability: number;
  sponsorValue: number;
};

export type HiddenDriverAttributes = {
  potential: number;
  developmentRate: number;
  clutchFactor: number;
  crashProneness: number;
  loyalty: number;
  adaptationCeiling: number;
  retirementChance: number;
};

export type Driver = {
  id: string;
  name: string;
  nationality: string;
  age: number;
  series: DriverSeries;
  teamId: string;
  academyId: string | null;
  attributes: DriverAttributes;
  hidden: HiddenDriverAttributes;
  currentForm: number;
  fatigue: number;
  morale: number;
};

export type Team = {
  id: string;
  name: string;
  series: TeamSeries;
  country: string;
  carPerformance: number;
  reliability: number;
  strategy: number;
  developmentRate: number;
  financialHealth: number;
  academyId: string | null;
  hiringProfile?: string | null;
  seatSecurity?: number | null;
};

export type Academy = {
  id: string;
  name: string;
  style: string;
  f1TeamId: string | null;
  supportLevel: number;
  pressure: number;
  patience: number;
  politicalStability: number;
  testingOpportunities: number;
  contractStrictness: number;
  mediaExpectations: number;
};

export type Track = {
  id: string;
  name: string;
  country: string;
  baseLapTime: number;
  overtakingDifficulty: number;
  tireDeg: number;
  safetyCarChance: number;
  rainChance: number;
  qualifyingImportance: number;
  streetCircuit: boolean;
  drsStrength: number;
  setupComplexity: number;
};

export type CalendarRound = {
  id: string;
  roundNumber: number;
  name: string;
  trackId: string;
  startDate: string;
  endDate: string;
  country: string;
  series: "F2";
  hasSprint: boolean;
  completed: boolean;
};

export type DataBootstrap = {
  f1Drivers: Driver[];
  f2Drivers: Driver[];
  f1Teams: Team[];
  f2Teams: Team[];
  academies: Academy[];
  tracks: Track[];
  f2Calendar: CalendarRound[];
};
