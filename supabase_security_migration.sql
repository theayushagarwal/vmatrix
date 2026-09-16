-- ============================================================================
-- Vmatrix Social OS: Supabase Security & Row-Level Security (RLS) Hardening
-- ============================================================================

-- 1. Enable Row-Level Security on 'posts'
ALTER TABLE public.posts ENABLE ROW LEVEL SECURITY;

-- Drop prior policies
DROP POLICY IF EXISTS Public read access for published posts ON public.posts;
DROP POLICY IF EXISTS Service role full access on posts ON public.posts;

-- Allow public read-only access to published posts
CREATE POLICY Public read access for published posts
ON public.posts
FOR SELECT
TO anon, authenticated
USING (true);

-- Restrict all write operations (INSERT, UPDATE, DELETE) strictly to the service_role key
CREATE POLICY Service role full access on posts
ON public.posts
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);


-- 2. Create missing 'competitor_posts' table
CREATE TABLE IF NOT EXISTS public.competitor_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shortcode TEXT UNIQUE NOT NULL,
    handle TEXT NOT NULL,
    niche TEXT DEFAULT 'AI & CODING',
    post_url TEXT,
    media_url TEXT,
    caption TEXT,
    likes BIGINT DEFAULT 0,
    views BIGINT DEFAULT 0,
    comments BIGINT DEFAULT 0,
    posted_at TEXT,
    is_reel SMALLINT DEFAULT 0,
    virality_analysis JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Enable RLS on 'competitor_posts'
ALTER TABLE public.competitor_posts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS Allow read access to competitor_posts ON public.competitor_posts;
DROP POLICY IF EXISTS Service role full access on competitor_posts ON public.competitor_posts;

-- Allow read access
CREATE POLICY Allow read access to competitor_posts
ON public.competitor_posts
FOR SELECT
TO anon, authenticated
USING (true);

-- Restrict writes strictly to service_role
CREATE POLICY Service role full access on competitor_posts
ON public.competitor_posts
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);


-- 3. High-performance lookup indices
CREATE INDEX IF NOT EXISTS idx_posts_title ON public.posts(title);
CREATE INDEX IF NOT EXISTS idx_competitor_posts_shortcode ON public.competitor_posts(shortcode);
CREATE INDEX IF NOT EXISTS idx_competitor_posts_handle ON public.competitor_posts(handle);
