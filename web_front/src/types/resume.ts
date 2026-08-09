export interface WorkExperience {
  company: string;
  role: string;
  duration: string;
  description: string;
}

export interface Education {
  school: string;
  degree: string;
  major: string;
  year: string;
}

export interface ParsedResumeContent {
  name: string;
  skills: string[];
  experience: WorkExperience[];
  education: Education;
}

export interface Resume {
  id: string;
  fileName: string;
  uploadTime: string;
  status: 'parsing' | 'ready' | 'error';
  parsedContent?: ParsedResumeContent;
}