/** HTTP stream alignment uses absolute seconds from the start of the utterance. */
export type Alignment = {
  characters: string[];
  character_start_times_seconds: number[];
  character_end_times_seconds: number[];
};
export type CaptionWord = { text: string; start: number; end: number };
export class CaptionTimeline {
  private letters: { text: string; start: number; end: number }[] = [];
  append(alignment: Alignment | null | undefined) {
    if (!alignment) return;
    const {
      characters,
      character_start_times_seconds: starts,
      character_end_times_seconds: ends,
    } = alignment;
    if (
      !Array.isArray(characters) ||
      characters.length !== starts?.length ||
      characters.length !== ends?.length
    )
      throw new Error(
        "Speech timing was incomplete. Your text answer is available.",
      );
    characters.forEach((text, i) => {
      if (
        !Number.isFinite(starts[i]) ||
        !Number.isFinite(ends[i]) ||
        ends[i] < starts[i]
      )
        throw new Error(
          "Speech timing was invalid. Your text answer is available.",
        );
      this.letters.push({
        text,
        start: starts[i],
        end: ends[i],
      });
    });
  }
  words(): CaptionWord[] {
    const words: CaptionWord[] = [];
    let pending: CaptionWord | undefined;
    for (const letter of this.letters) {
      if (/\s/.test(letter.text)) {
        if (pending) words.push(pending);
        pending = undefined;
      } else if (pending) {
        pending.text += letter.text;
        pending.end = letter.end;
      } else pending = { ...letter };
    }
    if (pending) words.push(pending);
    return words;
  }
}
