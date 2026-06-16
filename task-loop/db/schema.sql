-- task-loop harness schema (Supabase / Postgres).
-- One shared database; every repo is a row, every task is a row scoped by project.
-- Idempotent: safe to run on first setup and on every later `init`.

create table if not exists projects (
  id             text primary key,                 -- "owner/repo" (from git remote)
  default_branch text not null default 'main',
  next_seq       int  not null default 1,          -- per-project task counter
  created_at     timestamptz not null default now()
);

create table if not exists tasks (
  id          uuid primary key default gen_random_uuid(),   -- internal; never shown
  project_id  text not null references projects(id),
  seq         int  not null,                                 -- the CLI-facing id (001..)
  title       text not null,
  status      text not null default 'open'
              check (status in ('open','working','closed')),
  deps        int[] not null default '{}',                   -- per-project seqs this waits on
  issue       int,                                           -- GitHub issue # (human mirror)
  created_at  timestamptz not null default now(),
  unique (project_id, seq)
);

create index if not exists tasks_project_status on tasks (project_id, status);

-- RLS on with NO policies: only the secret / service_role key (which bypasses RLS)
-- can read/write these tables; the public anon / publishable key is denied. The CLI
-- uses the secret key, so it is unaffected. Add policies later only if you ever want
-- anon/authenticated access (e.g. a read-only dashboard).
alter table projects enable row level security;
alter table tasks    enable row level security;

-- claimable = open, with every dependency closed (a missing/not-closed dep blocks it).
-- security_invoker = on: the view respects the QUERIER's RLS (the secret key bypasses it;
-- the public anon key is denied). Without this, a view runs as its owner and would leak
-- tasks past the RLS enabled above.
create or replace view claimable
with (security_invoker = on) as
  select t.*
  from tasks t
  where t.status = 'open'
    and not exists (
      select 1
      from unnest(t.deps) as d
      left join tasks dep
        on dep.project_id = t.project_id and dep.seq = d
      where dep.status is distinct from 'closed'
    );

-- add a task; assigns the next per-project seq atomically; returns the seq
create or replace function task_add(p_project text, p_title text,
                                    p_deps int[] default '{}', p_issue int default null)
returns int language plpgsql as $$
declare s int;
begin
  select next_seq into s from projects where id = p_project for update;
  update projects set next_seq = s + 1 where id = p_project;
  insert into tasks (project_id, seq, title, deps, issue)
    values (p_project, s, p_title, coalesce(p_deps, '{}'), p_issue);
  return s;
end $$;

-- atomically claim the next ready task; returns the row, or null if none.
-- FOR UPDATE SKIP LOCKED makes concurrent orchestrators race-free.
create or replace function task_claim(p_project text)
returns tasks language plpgsql as $$
declare t tasks;
begin
  select tk.* into t
  from tasks tk
  where tk.project_id = p_project
    and tk.status = 'open'
    and not exists (
      select 1
      from unnest(tk.deps) as d
      left join tasks dep
        on dep.project_id = tk.project_id and dep.seq = d
      where dep.status is distinct from 'closed'
    )
  order by tk.seq
  for update skip locked
  limit 1;

  if not found then
    return null;
  end if;

  update tasks
     set status = 'working'
   where id = t.id
   returning * into t;
  return t;
end $$;
