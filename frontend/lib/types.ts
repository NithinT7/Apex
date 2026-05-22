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
  driverNumber?: number | null;
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
  series: "F1" | "F2";
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
  f1Calendar: CalendarRound[];
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
  category: "race" | "media" | "academy" | "rumor" | "contract" | "incident" | "system" | "rivalry";
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

export type WeatherState = {
  condition: "dry" | "damp" | "wet";
  airTemp: number;
  trackTemp: number;
  rainIntensity: number;
  trackGrip: number;
};

export type PracticeClassification = {
  position: number;
  driverId: string;
  lapTime: number;
  setupScore: number;
  note: string;
};

export type QualifyingClassification = {
  position: number;
  driverId: string;
  lapTime: number;
  gapToPole: number;
  note: string;
};

export type RunningOrderEntry = {
  position: number;
  driverId: string;
  gapToLeader: number;
  gapToCarAhead: number;
  currentLapTime: number | null;
  previousLapTime: number | null;
  bestLapTime: number | null;
  tireCompound: "soft" | "medium" | "hard" | "inter" | "wet";
  tireAge: number;
  tireWear: number;
  componentWear: number;
  status: "running" | "dnf";
};

export type DecisionChoice = {
  id: string;
  label: string;
  risk: number;
  effects: Record<string, number | string>;
};

export type DecisionPrompt = {
  id: string;
  lap: number;
  type:
    | "start"
    | "attack"
    | "defend"
    | "tires"
    | "strategy"
    | "safety_car"
    | "weather"
    | "late_pressure";
  title: string;
  description: string;
  defaultChoiceId: string;
  choices: DecisionChoice[];
};

export type LapSnapshot = {
  lap: number;
  runningOrder: RunningOrderEntry[];
  commentary: string[];
  safetyCar: boolean;
  weather: WeatherState;
  decisionPrompt: DecisionPrompt | null;
};

export type RaceClassification = {
  position: number;
  driverId: string;
  status: "running" | "dnf";
  totalTime: number;
  gapToWinner: number;
  points: number;
  pitStops: number;
  fastestLap: number;
};

export type RaceResult = {
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
};

export type WeekendResult = {
  saveId: string;
  roundId: string;
  trackId: string;
  completed: boolean;
  practice: {
    trackId: string;
    weather: WeatherState;
    classification: PracticeClassification[];
  };
  qualifying: {
    trackId: string;
    weather: WeatherState;
    classification: QualifyingClassification[];
  };
  sprint: RaceResult;
  feature: RaceResult;
  headline: string;
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
  f1Standings?: ChampionshipState | null;
  news: NewsItem[];
  rivalries: Rivalry[];
  contracts: Contract[];
  weekendResults: WeekendResult[];
  f1WeekendResults: WeekendResult[];
  development: DevelopmentState;
  randomSeed: number;
  eventFlags: Record<string, boolean | string | number>;
};

export type DevelopmentState = {
  availablePoints: number;
  totalEarned: number;
  spentPoints: Record<string, number>;
};

export type SaveSummary = {
  saveId: string;
  name: string;
  updatedAt: string;
  season: number;
  phase: CareerPhase;
  playerDriverId: string | null;
};

export type DriverBackground = {
  id: string;
  name: string;
  description: string;
  attributeEffects: Record<string, number>;
  hiddenEffects: Record<string, number>;
};

export type DriverArchetype = {
  id: string;
  name: string;
  description: string;
  attributeEffects: Record<string, number>;
  hiddenEffects: Record<string, number>;
};

export type CareerCreationOptions = {
  backgrounds: DriverBackground[];
  archetypes: DriverArchetype[];
  f2Teams: Team[];
  academies: Academy[];
};

export type CreateCareerPayload = {
  name: string;
  nationality: string;
  age: number;
  driverNumber: number;
  backgroundId: string;
  archetypeId: string;
  teamId: string;
  academyId: string;
  difficulty: "casual" | "realistic" | "brutal";
};

// Interactive race decision types

export type DecisionOutcome = {
  decisionId: string;
  choiceId: string;
  choiceLabel: string;
  paceModifier: number;
  tireWearModifier: number;
  incidentRiskModifier: number;
  narrative: string;
};

export type PendingDecision = {
  prompt: DecisionPrompt;
  raceType: "sprint" | "feature";
  expiresAtLap: number;
};

export type DecisionResponse = {
  decisionId: string;
  choiceIndex: number;
};

export type ActiveRaceState = {
  saveId: string;
  roundId: string;
  raceType: "sprint" | "feature";
  currentLap: number;
  totalLaps: number;
  lapSnapshots: LapSnapshot[];
  pendingDecision: PendingDecision | null;
  decisionHistory: DecisionOutcome[];
  isComplete: boolean;
  playerPosition: number | null;
  playerTireWear: number;
  safetyCarActive: boolean;
};

export type WeekendPrep = {
  roundId: string;
  hasSprint: boolean;
  practice: {
    trackId: string;
    weather: WeatherState;
    classification: PracticeClassification[];
  };
  qualifying: {
    trackId: string;
    weather: WeatherState;
    classification: QualifyingClassification[];
  };
  sprintGrid: string[];
  featureGrid: string[];
};

// Between-race activity types

export type ActivityType =
  | "rest"
  | "simulator"
  | "physical_training"
  | "media_appearance"
  | "sponsor_event"
  | "team_debrief"
  | "academy_meeting"
  | "fan_engagement"
  | "mental_coaching";

export type ActivityEffect = {
  fatigue: number;
  morale: number;
  form: number;
  academyTrust: number;
  reputation: number;
  sponsorValue: number;
};

export type Activity = {
  id: string;
  name: string;
  type: ActivityType;
  description: string;
  durationDays: number;
  baseEffects: ActivityEffect;
  riskChance: number;
  riskEffects: ActivityEffect | null;
  requirements: Record<string, number>;
};

export type ActivityOutcome = {
  activityId: string;
  activityName: string;
  success: boolean;
  narrative: string;
  effectsApplied: ActivityEffect;
};

export type AvailableActivities = {
  daysUntilNextRace: number;
  activities: Activity[];
  completedActivities: string[];
};

export type PlayerStatus = {
  fatigue: number;
  morale: number;
  form: number;
  reputation: number;
  sponsorValue: number;
  academyTrust: number | null;
  daysUntilRace: number;
  phase: CareerPhase;
};

export type SkillNode = {
  id: string;
  name: string;
  branch: string;
  description: string;
  attribute: string;
  cost: number;
  maxRank: number;
};

export type DevelopmentStatus = {
  availablePoints: number;
  totalEarned: number;
  spentPoints: Record<string, number>;
  skills: SkillNode[];
  attributes: Record<string, number>;
};
