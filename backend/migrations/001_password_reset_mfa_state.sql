ALTER TABLE app.jetons_reinitialisation_mot_de_passe
    ADD COLUMN IF NOT EXISTS type_token varchar(80) NULL,
    ADD COLUMN IF NOT EXISTS details jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS mfa_echecs_totp integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS mfa_dernier_echec_a timestamptz NULL,
    ADD COLUMN IF NOT EXISTS mfa_cooldown_jusqu_a timestamptz NULL,
    ADD COLUMN IF NOT EXISTS mfa_totp_bloque boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS mfa_echecs_recovery integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS mfa_recovery_bloque_jusqu_a timestamptz NULL;
