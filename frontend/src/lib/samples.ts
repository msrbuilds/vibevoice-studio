// Pre-built sample scripts for quick testing. Each sample declares its own
// speaker list (name + voice id) and a sequence of segments. Loading a
// sample replaces the current project's segments, speakers, and audio cache.

import type { Segment, Speaker } from "@/types/models";

export interface SampleSegment {
  speaker: string; // speaker name
  text: string;
}

export interface Sample {
  id: string;
  name: string;
  description: string;
  speakers: { name: string; voice: string; color: string }[];
  segments: SampleSegment[];
}

const SPEAKER_COLORS = [
  "#3b82f6", // blue
  "#10b981", // emerald
  "#f59e0b", // amber
  "#ef4444", // red
  "#8b5cf6", // violet
  "#ec4899", // pink
];

// Voices available in the default voices/ directory. The samples use these
// so they work out-of-the-box without requiring the user to have the
// historical en-Emma_woman / en-Carter_man etc. files.
//
// To customise: add your own .wav / .mp3 files to backend/voices/ and update
// these constants to match the new filenames (the filename stem is the id).
const DEFAULT_FEMALE_VOICE = "en_Amelia";
const DEFAULT_MALE_VOICE = "en_Mike";
const DEFAULT_URDU_MALE_VOICE = "ur_Hamza";
const DEFAULT_VOICE = DEFAULT_FEMALE_VOICE;

export const SAMPLES: Sample[] = [
  {
    id: "interview",
    name: "Two-host interview",
    description: "A short back-and-forth interview between two hosts.",
    speakers: [
      { name: "Host", voice: DEFAULT_FEMALE_VOICE, color: SPEAKER_COLORS[0]! },
      { name: "Guest", voice: DEFAULT_MALE_VOICE, color: SPEAKER_COLORS[1]! },
    ],
    segments: [
      {
        speaker: "Host",
        text: "Welcome back to the show. Today we're joined by a special guest to talk about the future of voice AI.",
      },
      {
        speaker: "Guest",
        text: "Thanks for having me. It's an exciting time. The quality of synthetic voices has improved dramatically over the past year.",
      },
      {
        speaker: "Host",
        text: "Absolutely. What do you think is driving that improvement?",
      },
      {
        speaker: "Guest",
        text: "A few things. Better training data, larger context windows, and diffusion-based decoders that produce much more natural prosody.",
      },
      {
        speaker: "Host",
        text: "And what about real-time applications? Are we there yet?",
      },
      {
        speaker: "Guest",
        text: "We're getting close. Sub-second latency is achievable, but there's still a trade-off between quality and speed.",
      },
      {
        speaker: "Host",
        text: "Fascinating. Thanks so much for joining us today.",
      },
      {
        speaker: "Guest",
        text: "Thanks for having me. It's been a great conversation.",
      },
    ],
  },
  {
    id: "narrator",
    name: "Single narrator",
    description: "A single narrator reads a short story passage.",
    speakers: [
      { name: "Narrator", voice: DEFAULT_MALE_VOICE, color: SPEAKER_COLORS[2]! },
    ],
    segments: [
      {
        speaker: "Narrator",
        text: "The morning fog rolled in from the bay, slow and deliberate, as if the city itself were exhaling. By the time Elena reached the corner of Fifth and Madison, the streetlights were still on, casting pale halos into the grey.",
      },
      {
        speaker: "Narrator",
        text: "She pulled her coat tighter and walked faster. The coffee shop on the next block would be opening soon, and she wanted to be there when the door unlocked. It had become a ritual, a small anchor in the drift of her weeks.",
      },
      {
        speaker: "Narrator",
        text: "Inside, the barista already knew her order. Outside, the city was waking up, one car at a time, one footstep at a time. Elena sat by the window, watched the fog lift, and let herself breathe.",
      },
    ],
  },
  {
    id: "panel",
    name: "Three-person panel",
    description: "A panel discussion with three speakers. Tests multi-speaker flow.",
    speakers: [
      { name: "Alice", voice: DEFAULT_FEMALE_VOICE, color: SPEAKER_COLORS[0]! },
      { name: "Bob", voice: DEFAULT_MALE_VOICE, color: SPEAKER_COLORS[1]! },
      { name: "Carol", voice: DEFAULT_FEMALE_VOICE, color: SPEAKER_COLORS[3]! },
    ],
    segments: [
      { speaker: "Alice", text: "Let's get started. Today's topic is the impact of AI on creative work." },
      { speaker: "Bob", text: "I think it's a tool, not a replacement. Like the calculator for arithmetic." },
      { speaker: "Carol", text: "I'd push back on that. The calculator doesn't make aesthetic choices." },
      { speaker: "Alice", text: "That's a fair point. Where do you draw the line, Carol?" },
      { speaker: "Carol", text: "I'd say AI is fine for brainstorming and rough drafts. The final voice should be human." },
      { speaker: "Bob", text: "But the line keeps moving. Five years ago, AI couldn't write a coherent paragraph." },
      { speaker: "Alice", text: "Good discussion. Let's pick this up next week with a concrete case study." },
    ],
  },
  {
    id: "tutorial",
    name: "How-to tutorial",
    description: "A friendly step-by-step explanation.",
    speakers: [
      { name: "Guide", voice: DEFAULT_FEMALE_VOICE, color: SPEAKER_COLORS[0]! },
    ],
    segments: [
      { speaker: "Guide", text: "Hi there. In the next two minutes, I'll show you how to set up a local text-to-speech pipeline." },
      { speaker: "Guide", text: "First, install the backend dependencies. We recommend a virtual environment, but a global install works too." },
      { speaker: "Guide", text: "Second, drop a short audio clip of your chosen voice into the voices directory. Ten to thirty seconds of clean speech is plenty." },
      { speaker: "Guide", text: "Third, start the server. The first launch will download the model weights, which takes a few minutes." },
      { speaker: "Guide", text: "Finally, open the frontend in your browser, pick a voice, and start generating. That's it!" },
    ],
  },
  {
    id: "kids",
    name: "Kids' story",
    description: "A whimsical short story for kids.",
    speakers: [
      { name: "Storyteller", voice: DEFAULT_FEMALE_VOICE, color: SPEAKER_COLORS[5]! },
    ],
    segments: [
      { speaker: "Storyteller", text: "Once upon a time, in a forest not far from here, there lived a little fox with a very shiny tail." },
      { speaker: "Storyteller", text: "Every morning, the fox would wake up, stretch all four legs, and set off to see what the day had in store." },
      { speaker: "Storyteller", text: "One Tuesday, the fox found a hat. Not just any hat, but a hat that hummed when you put it on." },
      { speaker: "Storyteller", text: "And from that day on, every adventure the fox had, big or small, was accompanied by a very cheerful tune." },
      { speaker: "Storyteller", text: "The end." },
    ],
  },
  {
    id: "urdu-hindi-chat",
    name: "Urdu/Hindi دو دوست (Two friends chat)",
    description: "A two-person podcast chat in Urdu/Hindi using Latin script (Roman Urdu/Hinglish).",
    speakers: [
      { name: "Ayesha", voice: DEFAULT_FEMALE_VOICE, color: SPEAKER_COLORS[0]! },
      { name: "Hamza", voice: DEFAULT_URDU_MALE_VOICE, color: SPEAKER_COLORS[1]! },
    ],
    segments: [
      {
        speaker: "Ayesha",
        text: "Assalamu alaikum Hamza, kya haal hain aap ke? Bohat din baad aaj podcast pe mil rahe hain.",
      },
      {
        speaker: "Hamza",
        text: "Walaikum assalam Ayesha, main bilkul theek hoon, shukriya. Haan, bohat din ho gaye. Aaj hum ek interesting topic pe baat karenge.",
      },
      {
        speaker: "Ayesha",
        text: "Ji bilkul. Aaj ka topic hai ke hum AI se apni zindagi mein kaise madad le sakte hain. Hamza, aap ka kya khayal hai?",
      },
      {
        speaker: "Hamza",
        text: "Dekhiye, AI ab sirf science fiction nahi raha. Ab yeh hamare phones mein, hamare ghar mein, aur ab humare studios mein bhi aa gaya hai.",
      },
      {
        speaker: "Ayesha",
        text: "Sach mein. Jaise yeh jo hum dono abhi use kar rahe hain, yeh local pe chal raha hai, bina internet ke, aur awaaz bhi bohat natural lag rahi hai.",
      },
      {
        speaker: "Hamza",
        text: "Haan, pehle ke text-to-speech systems robotic lagte the. Lekin ab aap ek chhoti si audio recording dein, aur AI usi awaaz mein kuch bhi bol sakta hai.",
      },
      {
        speaker: "Ayesha",
        text: "Aur sab se achi baat yeh hai ke yeh sab aap ke apne computer pe ho raha hai, kisi cloud pe nahi. Privacy bhi maintain rehti hai.",
      },
      {
        speaker: "Hamza",
        text: "Bilkul. Aap ki recording kabhi bahar nahi jaati. Aur languages bhi koi bhi ho sakti hai, Urdu, Hindi, English, kuch bhi.",
      },
      {
        speaker: "Ayesha",
        text: "Toh listeners, aap bhi try karein. Apni pasand ki awaaz record karein, aur koi bhi script likh kar is se bolwa lein.",
      },
      {
        speaker: "Hamza",
        text: "Shukriya Ayesha, aaj ke liye itna hi. Miltay hain agli episode mein.",
      },
      {
        speaker: "Ayesha",
        text: "Shukriya Hamza. Allah hafiz.",
      },
    ],
  },
];

export function loadSample(sample: Sample): {
  segments: Segment[];
  speakers: Speaker[];
} {
  const speakers: Speaker[] = sample.speakers.map((s, idx) => ({
    id: `sample-${sample.id}-speaker-${idx}`,
    name: s.name,
    voice: s.voice || DEFAULT_VOICE,
    color: s.color,
  }));
  // Map segment.speaker (name) to speakerId
  const nameToId = new Map(speakers.map((s) => [s.name, s.id]));
  const segments: Segment[] = sample.segments.map((seg) => ({
    id: crypto.randomUUID(),
    text: seg.text,
    speakerId: nameToId.get(seg.speaker) ?? speakers[0]?.id ?? null,
  }));
  return { segments, speakers };
}
