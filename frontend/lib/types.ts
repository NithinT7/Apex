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

export type CareerPhase = "preseason" | "race_week" | "between_races" | "offseason";

export type AcademyState = {
  academyId: string;
  trust: number;
  juniorDepth: string[];
  seatOpenings: number;
  politicalStability: number;
};

export type ChampionshipEntry = {
  driverId: string;
  points: number;
  wins: number;
  podiums: number;
  poles: number;
  fastestLaps: number;
  dnfs: number;
  penalties: number;
  averageQualifying: number;
  averageFinish: number;
};

export type ChampionshipState = {
  driverStandings: ChampionshipEntry[];
  teamStandings: Record<string, number>;
};

export type NewsItem = {
  id: string;
  date: string;
  category: "race" | "media" | "academy" | "rumor" | "contract" | "incident" | "system";
  headline: string;
  body: string;
  linkedDriverIds: string[];
  importance: number;
};

export type Rivalry = {
  rivalDriverId: string;
  type: "teammate" | "academy" | "championship" | "media" | "clean" | "dirty";
  intensity: number;
  respect: number;
  incidentHistory: number;
  mediaAttention: number;
  championshipStakes: number;
  academySeatConflict: boolean;
};

export type Contract = {
  id: string;
  driverId: string;
  teamId: string;
  role: "f1_race_seat" | "f1_reserve" | "f2_race_seat" | "academy_deal" | "loan_seat";
  startSeason: number;
  lengthYears: number;
  active: boolean;
};

export type SaveGame = {
  saveId: string;
  name: string;
  createdAt: string;
  updatedAt: string;
  currentDate: string;
  season: number;
  phase: CareerPhase;
  playerDriverId: string | null;
  drivers: Driver[];
  teams: Team[];
  academies: Academy[];
  academyStates: AcademyState[];
  calendar: CalendarRound[];
  standings: ChampionshipState;
  news: NewsItem[];
  rivalries: Rivalry[];
  contracts: Contract[];
  randomSeed: number;
  eventFlags: Record<string, boolean>;
};

export type SaveSummary = {
  saveId: string;
  name: string;
  updatedAt: string;
  season: number;
  phase: CareerPhase;
  playerDriverId: string | null;
};
