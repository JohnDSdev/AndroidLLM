package com.johndsdev.androidllm;

import java.util.function.Consumer;
import java.util.function.LongSupplier;

/** Main-thread display pacing; the inference producer only appends to source. */
public final class PrettyTextReveal {
    public interface Scheduler {
        void post(Runnable task, long delay);
        void remove(Runnable task);
    }
    private final StringBuilder source;
    private final boolean pretty;
    private final Scheduler scheduler;
    private final LongSupplier clock;
    private final Consumer<String> append;
    private int shown;
    private boolean cancelled;
    private Runnable completion;
    private long drainDeadline;
    private final Runnable frame = this::tick;

    public PrettyTextReveal(StringBuilder source, boolean pretty, Scheduler scheduler,
                            LongSupplier clock, Consumer<String> append) {
        this.source = source;
        this.pretty = pretty;
        this.scheduler = scheduler;
        this.clock = clock;
        this.append = append;
    }

    public void start() { scheduler.post(frame, 0); }

    private void tick() {
        if (cancelled) return;
        String delta;
        boolean caughtUp;
        synchronized (source) {
            int remaining = source.length() - shown;
            int step = Math.max(2, Math.min(16, remaining / 24));
            if (completion != null) {
                long timeLeft = Math.max(0, drainDeadline - clock.getAsLong());
                int framesLeft = Math.max(1, (int) ((timeLeft + 15) / 16));
                // Spread catch-up across the remaining frames instead of a final dump.
                step = Math.max(step, (remaining + framesLeft - 1) / framesLeft);
            }
            int end = pretty ? Math.min(shown + step, source.length()) : source.length();
            if (end < source.length() && end > shown && Character.isHighSurrogate(source.charAt(end - 1))) end++;
            delta = source.substring(shown, end);
            shown = end;
            caughtUp = shown == source.length();
        }
        if (!delta.isEmpty()) append.accept(delta);
        if (completion != null && caughtUp) {
            Runnable done = completion;
            cancel();
            done.run();
        } else {
            scheduler.post(frame, pretty ? 16 : 80);
        }
    }

    /** Called when native generation ends. Drain visually, without blocking it. */
    public void finish(Runnable complete) {
        if (cancelled) { complete.run(); return; }
        completion = complete;
        drainDeadline = clock.getAsLong() + 350;
    }

    /** Search replaces the response buffer on the UI thread. */
    public void reset() { shown = 0; }

    public void cancel() {
        cancelled = true;
        scheduler.remove(frame);
        completion = null;
    }
}
