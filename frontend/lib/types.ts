// Core types matching backend models (using camelCase to match API response)

export type CareerPhase = "preseason" | "race_week" | "between_races" | "offseason";
export type DifficultyPreset = "prodigy" | "realistic_prospect" | "underdog" | "brutal_realism";
export type ContractRole = "f1_race_seat" | "f1_reserve" | "f2_race_seat" | "academy_deal" | "loan_seat";
export type NewsCategory = "race" | "media" | "academy" | "rumor" | "contract" | "incident" | "system" | "rivalry";
export type TireCompound = "S" | "M" | "H" | "I" | "W";

export interface DriverAttributes {
  pace: number;
  qualifying: number;
  racecraft: number;
  consistency: number;
  tireManagement: number;
  wetWeather: number;
  starts: number;
  overtaking: number;
  defending: number;
  fuelManagement: number;
  technicalFeedback: number;
  adaptability: number;
  mentalFortitude: number;
}

export interface HiddenDriverAttributes {
  potential: number;
  growthRate: number;
  pressureHandling: number;
  luckFactor: number;
  mediaSavvy: number;
  teamPolitics: number;
  workEthic: number;
}

export interface DriverIdentity {
  primaryTrait: string | null;
  traitScores: Record<string, number>;
  summary: string;
}

export interface Driver {
  id: string;
  name: string;
  nationality: string;
  age: number;
  driverNumber: number;
  series: "F1" | "F2";
  teamId: string;
  academyId: string | null;
  attributes: DriverAttributes;
  hidden: HiddenDriverAttributes;
  identity: DriverIdentity;
  currentForm: number;
  fatigue: number;
  morale: number;
}

export interface Team {
  id: string;
  name: string;
  series: "F1" | "F2";
  country: string;
  carPerformance: number;
  reliability: number;
  strategy: number;
  developmentRate: number;
  financialHealth: number;
  academyId?: string | null;
}

export interface Academy {
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
}

export interface CalendarRound {
  id: string;
  name: string;
  country: string;
  trackId: string;
  roundNumber: number;
  series: "F1" | "F2";
  hasSprint: boolean;
  startDate: string;
  endDate: string;
  completed: boolean;
}

export interface ChampionshipEntry {
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
}

export interface ChampionshipState {
  driverStandings: ChampionshipEntry[];
  teamStandings: Record<string, number>;
}

export interface NewsItem {
  id: string;
  date: string;
  category: NewsCategory;
  headline: string;
  body: string;
  linkedDriverIds: string[];
  importance: number;
}

export interface Contract {
  id: string;
  driverId: string;
  teamId: string;
  role: ContractRole;
  startSeason: number;
  lengthYears: number;
  active: boolean;
}

export interface Rivalry {
  rivalDriverId: string;
  intensity: number;
  type: string;
  originRaceId?: string;
}

export interface AcademyState {
  academyId: string;
  trust: number;
  juniorDepth: string[];
  seatOpenings: number;
  politicalStability: number;
}

export interface RaceClassification {
  position: number;
  driverId: string;
  lapTime?: number;
  gapToWinner?: number;
  points: number;
  status: "finished" | "dnf";
  dnfReason?: string;
}

export interface LapSnapshot {
  lap: number;
  runningOrder: Array<{
    position: number;
    driverId: string;
    gap: number;
    tireCompound: TireCompound;
    tireAge: number;
    status: "running" | "dnf" | "pit";
  }>;
  commentary: string[];
  decisionPrompt?: boolean;
}

export interface DecisionPrompt {
  id: string;
  lap: number;
  title: string;
  description: string;
  choices: Array<{
    id: string;
    label: string;
    description: string;
    riskLevel: "low" | "medium" | "high";
  }>;
}

export interface SessionResult {
  trackId: string;
  classification: RaceClassification[];
  segments?: Array<{
    segment: string;
    classification: Array<{
      position: number;
      driverId: string;
      lapTime: number;
      gapToPole: number;
      note: string;
    }>;
    eliminated: string[];
    stories: string[];
  }>;
}

export interface RaceResult {
  raceId: string;
  sessionType: "sprint" | "feature";
  trackId: string;
  totalLaps: number;
  startingGrid: string[];
  classification: RaceClassification[];
  lapLog: LapSnapshot[];
  decisionPrompts: DecisionPrompt[];
  safetyCarLaps: number[];
  dnfs: string[];
}

export interface WeekendResult {
  roundId: string;
  headline: string;
  practice: SessionResult;
  qualifying: SessionResult;
  sprint: RaceResult;
  feature: RaceResult;
}

export interface DevelopmentProfile {
  availablePoints: number;
  totalEarned: number;
  branches: Record<string, {
    level: number;
    xp: number;
    unlockedNodes: string[];
  }>;
}

export interface SaveGame {
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
  f1Standings: ChampionshipState | null;
  news: NewsItem[];
  rivalries: Rivalry[];
  contracts: Contract[];
  weekendResults: WeekendResult[];
  f1WeekendResults: WeekendResult[];
  developmentProfile: DevelopmentProfile | null;
  difficulty: DifficultyPreset;
  randomSeed: number;
}

export interface SaveSummary {
  saveId: string;
  name: string;
  updatedAt: string;
  season: number;
  phase: CareerPhase;
  playerDriverId: string | null;
}

// Career creation types
export interface DriverBackground {
  id: string;
  name: string;
  description: string;
  attributeEffects: Record<string, number>;
  hiddenEffects: Record<string, number>;
}

export interface DriverArchetype {
  id: string;
  name: string;
  description: string;
  attributeEffects: Record<string, number>;
  hiddenEffects: Record<string, number>;
}

export interface F2Team {
  id: string;
  name: string;
  series: "F1" | "F2";
  country: string;
  carPerformance: number;
  reliability: number;
  strategy: number;
  developmentRate: number;
  financialHealth: number;
}

export interface CareerOptions {
  backgrounds: DriverBackground[];
  archetypes: DriverArchetype[];
  f2Teams: F2Team[];
  academies: Academy[];
  difficultyPresets: Array<{
    id: DifficultyPreset;
    name: string;
    description: string;
  }>;
}

export interface CreateCareerRequest {
  name: string;
  nationality: string;
  age: number;
  driver_number: number;
  background_id: string;
  archetype_id: string;
  team_id: string;
  academy_id: string;
  difficulty: DifficultyPreset;
}

// Weekend preview
export interface WeekendPreview {
  saveId: string;
  roundId: string;
  roundName: string;
  roundNumber: number;
  series: "F1" | "F2";
  hasSprint: boolean;
  track: {
    id: string;
    name: string;
    country: string;
    overtakingDifficulty: number;
    tireDeg: number;
    safetyCarChance: number;
    rainChance: number;
    qualifyingImportance: number;
    streetCircuit: boolean;
  };
  storylines: Array<{
    id: string;
    type: string;
    headline: string;
    narrative: string;
    dramaLevel: number;
    driverIds: string[];
    teamIds: string[];
  }>;
  championshipContext: {
    playerPosition: number;
    pointsToLeader: number;
    pointsToNext: number;
    pointsFromBehind: number;
    roundsRemaining: number;
    titleInReach: boolean;
    relegationDanger: boolean;
  };
  playerForm: number | null;
  playerMorale: number | null;
  teammateName: string | null;
  weatherForecast: {
    condition: "dry" | "wet";
    airTemp: number;
    trackTemp: number;
    rainIntensity: number;
    trackGrip: number;
  };
}
