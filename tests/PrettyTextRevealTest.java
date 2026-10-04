import com.johndsdev.androidllm.PrettyTextReveal;
import java.util.PriorityQueue;

public class PrettyTextRevealTest {
    static class Clock implements PrettyTextReveal.Scheduler {
        long now;
        static class Job implements Comparable<Job> {
            long at; Runnable runnable;
            Job(long at, Runnable runnable) { this.at = at; this.runnable = runnable; }
            public int compareTo(Job other) { return Long.compare(at, other.at); }
        }
        final PriorityQueue<Job> jobs = new PriorityQueue<>();
        public void post(Runnable r, long delay) { jobs.add(new Job(now + delay, r)); }
        public void remove(Runnable r) { jobs.removeIf(j -> j.runnable == r); }
        void advance(long duration) {
            long end = now + duration;
            while (!jobs.isEmpty() && jobs.peek().at <= end) {
                Job job = jobs.remove(); now = job.at; job.runnable.run();
            }
            now = end;
        }
    }
    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
    public static void main(String[] args) {
        Clock clock = new Clock(); StringBuilder source = new StringBuilder();
        StringBuilder displayed = new StringBuilder(); boolean[] completed = {false};
        PrettyTextReveal reveal = new PrettyTextReveal(source, true, clock, () -> clock.now, displayed::append);
        reveal.start(); source.append("a short answer that finishes before its animation");
        reveal.finish(() -> completed[0] = true);
        check(!completed[0], "inference finishing must not cancel pending pretty text");
        clock.advance(16);
        check(displayed.length() > 0 && displayed.length() < source.length(), "pretty text must reveal gradually");
        clock.advance(600);
        check(completed[0] && displayed.toString().equals(source.toString()), "completion must drain every character");
        check(clock.jobs.isEmpty(), "completion must release callbacks");

        Clock emojiClock = new Clock(); StringBuilder emoji = new StringBuilder("a😀b😀c");
        StringBuilder emojiOutput = new StringBuilder();
        PrettyTextReveal emojiReveal = new PrettyTextReveal(emoji, true, emojiClock, () -> emojiClock.now, delta -> {
            check(!Character.isHighSurrogate(delta.charAt(delta.length()-1)), "split emoji at frame boundary");
            emojiOutput.append(delta);
        });
        emojiReveal.start(); emojiClock.advance(100);
        check(emojiOutput.toString().equals(emoji.toString()), "emoji text changed");
        emojiReveal.cancel(); check(emojiClock.jobs.isEmpty(), "cancel leaves callbacks");

        Clock longClock = new Clock(); StringBuilder longText = new StringBuilder("x".repeat(40000));
        StringBuilder longOutput = new StringBuilder(); boolean[] longDone = {false};
        int[] largestFrame = {0};
        PrettyTextReveal longReveal = new PrettyTextReveal(longText, true, longClock, () -> longClock.now, delta -> {
            largestFrame[0] = Math.max(largestFrame[0], delta.length());
            longOutput.append(delta);
        });
        longReveal.start(); longReveal.finish(() -> longDone[0] = true); longClock.advance(400);
        check(longDone[0] && longOutput.length()==longText.length(), "long response drain must be bounded");
        check(largestFrame[0] < longText.length() / 8, "catch-up must be spread across frames");

        Clock plainClock = new Clock(); StringBuilder plainOutput = new StringBuilder();
        PrettyTextReveal plain = new PrettyTextReveal(new StringBuilder("plain text"), false, plainClock, () -> plainClock.now, plainOutput::append);
        plain.start(); plainClock.advance(0);
        check(plainOutput.toString().equals("plain text"), "disabled pretty mode must not throttle output");
        plain.cancel();
        System.out.println("PASS: pretty completion, gradual reveal, emoji boundaries, callback cleanup, bounded backlog, plain mode");
    }
}
