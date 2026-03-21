CREATE TABLE wallets (
    id                  UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id             TEXT NOT NULL UNIQUE,        
    username            TEXT NOT NULL,               
 
    pin_hash            TEXT NOT NULL,               
    seed_phrase         TEXT NOT NULL,               
    
    ltc_address         TEXT NOT NULL,               
    ltc_private_key     TEXT NOT NULL,               

    sol_address         TEXT NOT NULL,               
    sol_private_key     TEXT NOT NULL,               
 
    created_at          TIMESTAMPTZ DEFAULT now(),   
    last_accessed       TIMESTAMPTZ DEFAULT now()    
);
 
CREATE INDEX idx_wallets_user_id ON wallets (user_id);

CREATE OR REPLACE FUNCTION update_last_accessed()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_accessed = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
 
CREATE TRIGGER trg_update_last_accessed
    BEFORE UPDATE ON wallets
    FOR EACH ROW
    EXECUTE FUNCTION update_last_accessed();
 