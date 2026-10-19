
-- Shoir-IE production persistence boundary hardening.
-- These custom-auth tables are consumed by the server-side persistence layer,
-- not directly by the Supabase Data API. Keep them inaccessible to anon/authenticated.
revoke all on table public.shoir_accounts from anon, authenticated;
revoke all on table public.shoir_subscription_requests from anon, authenticated;
revoke all on table public.shoir_workspace_states from anon, authenticated;
revoke all on table public.shoir_pending_credentials from anon, authenticated;
revoke all on table public.shoir_sessions from anon, authenticated;

alter table public.shoir_accounts enable row level security;
alter table public.shoir_subscription_requests enable row level security;
alter table public.shoir_workspace_states enable row level security;
alter table public.shoir_pending_credentials enable row level security;
alter table public.shoir_sessions enable row level security;

drop policy if exists "server_only_shoir_accounts" on public.shoir_accounts;
drop policy if exists "server_only_shoir_subscription_requests" on public.shoir_subscription_requests;
drop policy if exists "server_only_shoir_workspace_states" on public.shoir_workspace_states;
drop policy if exists "server_only_shoir_pending_credentials" on public.shoir_pending_credentials;
drop policy if exists "server_only_shoir_sessions" on public.shoir_sessions;

create policy "server_only_shoir_accounts" on public.shoir_accounts
  for all to anon, authenticated using (false) with check (false);
create policy "server_only_shoir_subscription_requests" on public.shoir_subscription_requests
  for all to anon, authenticated using (false) with check (false);
create policy "server_only_shoir_workspace_states" on public.shoir_workspace_states
  for all to anon, authenticated using (false) with check (false);
create policy "server_only_shoir_pending_credentials" on public.shoir_pending_credentials
  for all to anon, authenticated using (false) with check (false);
create policy "server_only_shoir_sessions" on public.shoir_sessions
  for all to anon, authenticated using (false) with check (false);

revoke execute on function public.shoir_cleanup_sessions() from public, anon, authenticated;
