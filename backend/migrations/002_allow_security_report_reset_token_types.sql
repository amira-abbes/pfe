ALTER TABLE app.jetons_reinitialisation_mot_de_passe
    DROP CONSTRAINT IF EXISTS chk_reset_type_token;

ALTER TABLE app.jetons_reinitialisation_mot_de_passe
    ADD CONSTRAINT chk_reset_type_token
    CHECK (
        type_token IS NULL OR type_token IN (
            'PASSWORD_RESET',
            'PASSWORD_RESET_FROM_LOCKOUT',
            'RESET_PASSWORD_RECOVERY_CODE',
            'MFA_BACKUP_CODE',
            'MFA_RESET',
            'SECURITY_REPORT'
        )
    );

ALTER TABLE app.jetons_reinitialisation_mot_de_passe
    DROP CONSTRAINT IF EXISTS chk_reset_type_jeton;

ALTER TABLE app.jetons_reinitialisation_mot_de_passe
    ADD CONSTRAINT chk_reset_type_jeton
    CHECK (
        type_jeton IN (
            'PASSWORD_RESET',
            'PASSWORD_RESET_FROM_LOCKOUT',
            'RESET_PASSWORD_RECOVERY_CODE',
            'MFA_BACKUP_CODE',
            'MFA_RESET',
            'SECURITY_REPORT'
        )
    );
