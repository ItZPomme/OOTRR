// Générateur de seed natif : portage exact de ootrr/search.py et ootrr/fill.py (voir generator.hpp).
// Les ordres de parcours et de tirage suivent ceux de Python pour obtenir exactement les mêmes seeds.
#include "generator.hpp"

#include "py_random.hpp"

namespace ootrr {
namespace {

using namespace logic;

constexpr int kChild = 0;
constexpr int kAdult = 1;

// ------------------------------------------------------------------ monde selon les réglages
struct World {
    const Settings* settings;
    int32_t item_logic[kItemCount];      // capacité donnée, -1 si aucune (cœurs hors pont « hearts »)
    bool loc_shuffle[kLocationCount];
    int32_t loc_region[kLocationCount];
    int32_t loc_rule[kLocationCount];    // -1 = toujours vrai (objet donné au départ)
    bool free_return;
    // sorties par région, dans l'ordre des données
    int16_t exit_first[kRegionCount + 1];
    int16_t exit_list[kExitCount];

    void Init(const Settings& s) {
        settings = &s;
        bool hearts_bridge = s[SET_bridge] == kBridgeHearts;
        for (int i = 0; i < kItemCount; i++)
            item_logic[i] = (kItems[i].heart && !hearts_bridge) ? -1 : kItems[i].logic;
        bool start[kLocationCount] = {};
        if (s[SET_open_door_of_time]) {
            for (int32_t l : kOpenDoorStart) start[l] = true;
        } else if (s[SET_skip_child_zelda]) {
            for (int32_t l : kSkipChildZelda) start[l] = true;
        }
        bool skip_rauru = s[SET_skip_cutscenes] == kSkipSafe || s[SET_shuffle_rewards] != kRewardsVanilla;
        if (skip_rauru) start[kLinksPocket] = true;
        for (int l = 0; l < kLocationCount; l++) {
            const LocationInfo& info = kLocations[l];
            loc_region[l] = start[l] ? kRoot : info.region;
            loc_rule[l] = start[l] ? -1 : info.rule;
            bool shuffle = info.shuffle;
            if (info.dungeon_item && s[SET_maps_compasses] == kMapsVanilla) shuffle = false;
            if (info.pickup) {
                int mode = s[SET_shuffle_hearts];
                shuffle = mode == kHeartsAll || (mode == kHeartsFreestanding && info.pickup == 1);
                if (info.pickup == 3) shuffle = s[SET_shuffle_gifts] != 0;  // objet au sol unique (Flèche de feu)
            }
            if (info.scrub) shuffle = s[SET_shuffle_scrubs] != 0;
            if (info.skulltula) {
                int mode = s[SET_shuffle_skulltulas];
                shuffle = mode == kSkulltulasAll || (mode == kSkulltulasOverworld && info.dungeon < 0);
            }
            if (info.shop) shuffle = info.shop <= s[SET_shuffle_shops];  // valeur 0..4 = nombre d'articles
            if (info.ocarina) shuffle = s[SET_shuffle_ocarinas] != 0;
            if (info.kind == kKindSong) shuffle = s[SET_shuffle_songs] == kSongsRandom;
            if (info.gift) shuffle = s[SET_shuffle_gifts] != 0;
            loc_shuffle[l] = shuffle;
        }
        free_return = s[SET_free_time_travel] != 0;
        int n = 0;
        for (int r = 0; r < kRegionCount; r++) {
            exit_first[r] = static_cast<int16_t>(n);
            for (int e = 0; e < kExitCount; e++)
                if (kExits[e].source == r) exit_list[n++] = static_cast<int16_t>(e);
        }
        exit_first[kRegionCount] = static_cast<int16_t>(n);
    }

    bool IsProgression(int item) const { return item >= 0 && item_logic[item] >= 0; }

    static bool IsRupee(const char* name) {
        const char* prefix = "TBox_Rupee_";
        while (*prefix && *name == *prefix) { name++; prefix++; }
        return !*prefix;
    }

    bool CanPlace(int item, int loc) const {
        const LocationInfo& info = kLocations[loc];
        if (info.pickup && !kItems[item].ground) return false;
        if (info.skulltula && !kItems[item].ground) return false;  // lâché par la Skulltula : ramassable
        // Peste Mojo : objets « au sol », sauf les rubis (un rubis vendu n'irait pas dans la bourse)
        if (info.scrub && (!kItems[item].ground || IsRupee(kItems[item].name))) return false;
        if (info.shop && !kItems[item].ground) return false;  // vendu par le jeton (rubis ajoutés par le module)
        if (info.ocarina) {  // pas de bombes données par Saria / les douves (world.OCARINA_FORBIDDEN_PREFIX)
            const char* name = kItems[item].name;
            const char* prefix = "Item_BombBundle";
            while (*prefix && *name == *prefix) { name++; prefix++; }
            if (!*prefix) return false;
        }
        if (info.gift) {  // ni bombes (sac) ni rubis (pas d'inventaire) : world.can_place
            const char* name = kItems[item].name;
            const char* prefix = "Item_BombBundle";
            while (*prefix && *name == *prefix) { name++; prefix++; }
            if (!*prefix) return false;
            if (IsRupee(kItems[item].name)) return false;
        }
        if (info.no_progression && IsProgression(item)) return false;
        return true;
    }

    void Collect(int16_t* inventory, int item) const {
        int logic = item_logic[item];
        if (logic < 0) return;
        int level = kItems[item].level;
        if (level == 0)
            inventory[logic]++;
        else if (inventory[logic] < level)
            inventory[logic] = static_cast<int16_t>(level);
    }
};

// ------------------------------------------------------------------ recherche (search.py)
struct State {
    const World* world;
    int16_t items[kInventoryCount];
    int16_t child_items[kInventoryCount];
    bool reached[2][kRegionCount];
    bool collected[kLocationCount];
    bool events[kInventoryCount];
    bool can_return;

    void Init(const World& w, const int16_t* start_items, int count) {
        world = &w;
        for (int i = 0; i < kInventoryCount; i++) items[i] = child_items[i] = 0, events[i] = false;
        for (int i = 0; i < count; i++) {
            w.Collect(items, start_items[i]);
            w.Collect(child_items, start_items[i]);
        }
        for (int a = 0; a < 2; a++)
            for (int r = 0; r < kRegionCount; r++) reached[a][r] = r == kRoot;
        for (int l = 0; l < kLocationCount; l++) collected[l] = false;
        can_return = w.free_return;
    }

    bool Has(int thing, int n, int age) const {
        if (age == kChild && !can_return) return child_items[thing] >= n;
        return items[thing] >= n;
    }

    // --- évaluation d'une règle (code préfixé)
    static int Skip(int pc) {
        switch (kCode[pc]) {
            case T_TRUE: case T_FALSE: case T_IS_CHILD: case T_IS_ADULT: return pc + 1;
            case T_HAS: return pc + 3;
            case T_HELPER: case T_SET_BOOL: return pc + 2;
            case T_SET_IS: return pc + 3;
            case T_NOT: return Skip(pc + 1);
            case T_AND: case T_OR: {
                int n = kCode[pc + 1];
                pc += 2;
                for (int i = 0; i < n; i++) pc = Skip(pc);
                return pc;
            }
            case T_CMP: return SkipNum(SkipNum(pc + 2));
            default: return pc + 1;
        }
    }

    static int SkipNum(int pc) {
        switch (kCode[pc]) {
            case N_CONST: case N_SETTING: return pc + 2;
            case N_COUNT: return pc + 2 + kCode[pc + 1];
            default: return pc + 1;  // N_HEARTS
        }
    }

    int Num(int& pc, int age) const {
        const Settings& s = *world->settings;
        switch (kCode[pc]) {
            case N_CONST: pc += 2; return kCode[pc - 1];
            case N_SETTING: pc += 2; return s[kCode[pc - 1]];
            case N_COUNT: {
                int n = kCode[pc + 1], total = 0;
                for (int i = 0; i < n; i++) total += Has(kCode[pc + 2 + i], 1, age) ? 1 : 0;
                pc += 2 + n;
                return total;
            }
            default: {  // N_HEARTS : 3 + réceptacles (max 20) + quarts (max 80) / 4
                pc += 1;
                int containers = 0, pieces = 0;
                for (int n = 1; n <= 20; n++) containers += Has(kHeartContainer, n, age) ? 1 : 0;
                for (int n = 1; n <= 80; n++) pieces += Has(kHeartPiece, n, age) ? 1 : 0;
                return 3 + containers + pieces / 4;
            }
        }
    }

    bool Eval(int& pc, int age) const {
        const Settings& s = *world->settings;
        switch (kCode[pc]) {
            case T_TRUE: pc += 1; return true;
            case T_FALSE: pc += 1; return false;
            case T_IS_CHILD: pc += 1; return age == kChild;
            case T_IS_ADULT: pc += 1; return age == kAdult;
            case T_HAS: pc += 3; return Has(kCode[pc - 2], kCode[pc - 1], age);
            case T_HELPER: {
                int sub = kHelpers[kCode[pc + 1]];
                pc += 2;
                return Eval(sub, age);
            }
            case T_SET_BOOL: pc += 2; return s[kCode[pc - 1]] != 0;
            case T_SET_IS: pc += 3; return s[kCode[pc - 2]] == kCode[pc - 1];
            case T_NOT: pc += 1; return !Eval(pc, age);
            case T_AND: case T_OR: {
                bool is_and = kCode[pc] == T_AND;
                int n = kCode[pc + 1];
                pc += 2;
                bool result = is_and;
                int i = 0;
                for (; i < n; i++) {
                    bool v = Eval(pc, age);
                    if (is_and ? !v : v) { result = !is_and; i++; break; }
                }
                for (; i < n; i++) pc = Skip(pc);
                return result;
            }
            case T_CMP: {
                int op = kCode[pc + 1];
                pc += 2;
                int a = Num(pc, age);
                int b = Num(pc, age);
                switch (op) {
                    case 0: return a >= b;
                    case 1: return a > b;
                    case 2: return a <= b;
                    case 3: return a < b;
                    case 4: return a == b;
                    default: return a != b;
                }
            }
            default: pc += 1; return false;
        }
    }

    bool Check(int rule, int age) const {
        if (rule < 0) return true;
        int pc = rule;
        return Eval(pc, age);
    }

    void Expand() {
        int16_t stack[kRegionCount];
        for (int age = 0; age < 2; age++) {
            int top = 0;
            for (int r = 0; r < kRegionCount; r++)
                if (reached[age][r]) stack[top++] = static_cast<int16_t>(r);
            while (top) {
                int r = stack[--top];
                for (int i = world->exit_first[r]; i < world->exit_first[r + 1]; i++) {
                    const Exit& ex = kExits[world->exit_list[i]];
                    if (!reached[age][ex.target] && Check(ex.rule, age)) {
                        reached[age][ex.target] = true;
                        stack[top++] = static_cast<int16_t>(ex.target);
                    }
                }
            }
        }
    }

    bool ReachAs(int region, int rule, int age) const { return reached[age][region] && Check(rule, age); }

    bool CanReach(int loc) const {
        return ReachAs(world->loc_region[loc], world->loc_rule[loc], kChild) ||
               ReachAs(world->loc_region[loc], world->loc_rule[loc], kAdult);
    }

    // une « sphère » (State.step) ; renvoie false au point fixe
    bool Step(const int16_t* placement) {
        Expand();
        int16_t found_event[kEventCount];
        bool event_child[kEventCount];
        int events_found = 0;
        for (int e = 0; e < kEventCount; e++) {
            const Event& ev = kEvents[e];
            if (!events[ev.thing] && (ReachAs(ev.region, ev.rule, kChild) || ReachAs(ev.region, ev.rule, kAdult))) {
                found_event[events_found] = static_cast<int16_t>(e);
                event_child[events_found++] = ReachAs(ev.region, ev.rule, kChild);
            }
        }
        int16_t found_loc[kLocationCount];
        bool loc_child[kLocationCount];
        int locs_found = 0;
        for (int l = 0; l < kLocationCount; l++) {
            if (placement[l] < 0 || collected[l] || !CanReach(l)) continue;
            found_loc[locs_found] = static_cast<int16_t>(l);
            loc_child[locs_found++] = ReachAs(world->loc_region[l], world->loc_rule[l], kChild);
        }
        for (int i = 0; i < events_found; i++) {
            int thing = kEvents[found_event[i]].thing;
            events[thing] = true;
            items[thing]++;
            if (event_child[i]) child_items[thing]++;
        }
        for (int i = 0; i < locs_found; i++) {
            int l = found_loc[i];
            collected[l] = true;
            world->Collect(items, placement[l]);
            if (loc_child[i]) world->Collect(child_items, placement[l]);
        }
        if (!can_return && items[kReturnToChild] && reached[kAdult][kTempleOfTime]) {
            can_return = true;
            for (int r = 0; r < kRegionCount; r++) reached[kChild][r] = r == kRoot;
        }
        return events_found + locs_found > 0;
    }

    void Sweep(const int16_t* placement) {
        while (Step(placement)) {
        }
    }

    bool Beaten() const { return events[kGoal]; }
};

// ------------------------------------------------------------------ placement (fill.py)
struct Fill {
    const World& w;
    PyRandom& rng;
    int16_t placement[kLocationCount];
    int16_t shuffled[kLocationCount];
    int shuffled_count = 0;

    // tampons (le générateur n'est pas réentrant)
    static inline State scratch;
    static inline int16_t candidates[kLocationCount][kLocationCount];
    static inline int16_t candidate_count[kLocationCount];

    Fill(const World& world, PyRandom& r) : w(world), rng(r) {}

    // lieux encore vides atteignables pour `item`, en supposant les autres objets de `assumed`
    int Candidates(int item, const int16_t* assumed, int assumed_count, int16_t* out) {
        int16_t without[kLocationCount];
        int n = 0;
        bool removed = false;
        for (int i = 0; i < assumed_count; i++) {
            if (!removed && assumed[i] == item) { removed = true; continue; }
            without[n++] = assumed[i];
        }
        scratch.Init(w, without, n);
        scratch.Sweep(placement);
        int count = 0;
        for (int i = 0; i < shuffled_count; i++) {
            int l = shuffled[i];
            if (placement[l] < 0 && w.CanPlace(item, l) && scratch.CanReach(l)) out[count++] = static_cast<int16_t>(l);
        }
        return count;
    }

    static void RemoveFirst(int16_t* list, int& count, int value) {
        for (int i = 0; i < count; i++) {
            if (list[i] != value) continue;
            for (int j = i; j + 1 < count; j++) list[j] = list[j + 1];
            count--;
            return;
        }
    }

    bool AssumedFill(int16_t* items, int count) {
        rng.Shuffle(items, count);
        int16_t assumed[kLocationCount];
        int assumed_count = count;
        for (int i = 0; i < count; i++) assumed[i] = items[i];
        while (count) {
            int16_t unique[kLocationCount];
            int unique_count = 0;
            for (int i = 0; i < count; i++) {
                bool seen = false;
                for (int j = 0; j < unique_count && !seen; j++) seen = unique[j] == items[i];
                if (!seen) unique[unique_count++] = items[i];
            }
            int best = -1;
            for (int u = 0; u < unique_count; u++) {
                candidate_count[u] = static_cast<int16_t>(Candidates(unique[u], assumed, assumed_count, candidates[u]));
                if (best < 0 || candidate_count[u] < candidate_count[best]) best = u;
            }
            if (candidate_count[best] == 0) return false;
            int item = unique[best];
            RemoveFirst(items, count, item);
            RemoveFirst(assumed, assumed_count, item);
            placement[candidates[best][rng.ChoiceIndex(candidate_count[best])]] = static_cast<int16_t>(item);
        }
        return true;
    }

    bool Attempt() {
        const Settings& s = *w.settings;
        for (int l = 0; l < kLocationCount; l++) placement[l] = w.loc_shuffle[l] ? -1 : static_cast<int16_t>(kLocations[l].vanilla);
        shuffled_count = 0;
        for (int l = 0; l < kLocationCount; l++)
            if (w.loc_shuffle[l]) shuffled[shuffled_count++] = static_cast<int16_t>(l);
        // réserve (World.pool) : (objet, donjon imposé ou -1)
        int16_t pool_item[kLocationCount], pool_dungeon[kLocationCount];
        bool maps_shuffle = s[SET_maps_compasses] == kMapsShuffle;
        for (int i = 0; i < shuffled_count; i++) {
            const LocationInfo& info = kLocations[shuffled[i]];
            if (info.dungeon_item && maps_shuffle) {
                pool_item[i] = static_cast<int16_t>(info.vanilla);
                pool_dungeon[i] = static_cast<int16_t>(info.dungeon);
            } else {
                pool_item[i] = static_cast<int16_t>(info.dungeon_item ? kJunk : info.vanilla);
                pool_dungeon[i] = -1;
            }
        }

        if (s[SET_shuffle_rewards] == kRewardsShuffled) {
            int16_t rewards[kLocationCount], reward_items[kLocationCount];
            int reward_count = 0;
            for (int l = 0; l < kLocationCount; l++)
                if (kLocations[l].kind == kKindReward) {
                    rewards[reward_count] = static_cast<int16_t>(l);
                    reward_items[reward_count++] = static_cast<int16_t>(kLocations[l].vanilla);
                }
            static int16_t trial[kLocationCount];
            for (int t = 0; t < 200; t++) {
                rng.Shuffle(reward_items, reward_count);
                for (int l = 0; l < kLocationCount; l++) trial[l] = placement[l];
                for (int i = 0; i < reward_count; i++) trial[rewards[i]] = reward_items[i];
                scratch.Init(w, pool_item, shuffled_count);
                scratch.Sweep(trial);
                if (scratch.Beaten()) break;
            }
            for (int i = 0; i < reward_count; i++) placement[rewards[i]] = reward_items[i];
        }
        if (s[SET_shuffle_songs] == kSongsShuffle) {  // chants mélangés entre eux (fill.py, même méthode)
            int16_t songs[kLocationCount], song_items[kLocationCount];
            int song_count = 0;
            for (int l = 0; l < kLocationCount; l++)
                if (kLocations[l].kind == kKindSong) {
                    songs[song_count] = static_cast<int16_t>(l);
                    song_items[song_count++] = static_cast<int16_t>(kLocations[l].vanilla);
                }
            static int16_t song_trial[kLocationCount];
            for (int t = 0; t < 200; t++) {
                rng.Shuffle(song_items, song_count);
                for (int l = 0; l < kLocationCount; l++) song_trial[l] = placement[l];
                for (int i = 0; i < song_count; i++) song_trial[songs[i]] = song_items[i];
                scratch.Init(w, pool_item, shuffled_count);
                scratch.Sweep(song_trial);
                if (scratch.Beaten()) break;
            }
            for (int i = 0; i < song_count; i++) placement[songs[i]] = song_items[i];
        }

        // 1. cartes et boussoles dans leur propre donjon
        for (int i = 0; i < shuffled_count; i++) {
            if (pool_dungeon[i] < 0) continue;
            int16_t free[kLocationCount];
            int n = 0;
            for (int j = 0; j < shuffled_count; j++) {
                int l = shuffled[j];
                if (kLocations[l].dungeon == pool_dungeon[i] && placement[l] < 0 && w.CanPlace(pool_item[i], l))
                    free[n++] = static_cast<int16_t>(l);
            }
            if (!n) return false;
            placement[free[rng.ChoiceIndex(n)]] = pool_item[i];
        }

        int16_t progression[kLocationCount], rest[kLocationCount];
        int progression_count = 0, rest_count = 0;
        for (int i = 0; i < shuffled_count; i++) {
            if (pool_dungeon[i] >= 0) continue;
            if (w.IsProgression(pool_item[i]))
                progression[progression_count++] = pool_item[i];
            else
                rest[rest_count++] = pool_item[i];
        }

        // 2. objets de progression
        if (!AssumedFill(progression, progression_count)) return false;

        // 3. le reste, d'abord les objets qui ont le moins de lieux possibles
        int16_t empty[kLocationCount];
        int empty_count = 0;
        for (int i = 0; i < shuffled_count; i++)
            if (placement[shuffled[i]] < 0) empty[empty_count++] = shuffled[i];
        if (empty_count != rest_count) return false;
        rng.Shuffle(rest, rest_count);
        int16_t key[kLocationCount];
        for (int i = 0; i < rest_count; i++) {
            int k = 0;
            for (int j = 0; j < empty_count; j++) k += w.CanPlace(rest[i], empty[j]) ? 1 : 0;
            key[i] = static_cast<int16_t>(k);
        }
        for (int i = 1; i < rest_count; i++) {  // tri stable (insertion), comme list.sort
            int16_t item = rest[i], k = key[i];
            int j = i - 1;
            while (j >= 0 && key[j] > k) {
                rest[j + 1] = rest[j];
                key[j + 1] = key[j];
                j--;
            }
            rest[j + 1] = item;
            key[j + 1] = k;
        }
        for (int i = 0; i < rest_count; i++) {
            int16_t free[kLocationCount];
            int n = 0;
            for (int j = 0; j < empty_count; j++)
                if (placement[empty[j]] < 0 && w.CanPlace(rest[i], empty[j])) free[n++] = empty[j];
            if (!n) return false;
            placement[free[rng.ChoiceIndex(n)]] = rest[i];
        }
        return true;
    }
};

}  // namespace

bool Generate(const Settings& settings, uint64_t seed, SeedResult& out, int max_attempts) {
    static World world;
    world.Init(settings);
    PyRandom rng(seed);
    Fill fill(world, rng);
    out.ok = false;
    for (int attempt = 1; attempt <= max_attempts; attempt++) {
        if (!fill.Attempt()) continue;
        static State check;
        check.Init(world, nullptr, 0);
        check.Sweep(fill.placement);
        if (!check.Beaten()) continue;
        if (settings[SET_accessibility] == kAccessibilityAll) {
            bool all = true;
            for (int l = 0; l < kLocationCount && all; l++) all = check.collected[l];
            if (!all) continue;
        }
        out.ok = true;
        out.attempts = attempt;
        for (int l = 0; l < kLocationCount; l++) out.placement[l] = fill.placement[l];
        return true;
    }
    return false;
}

}  // namespace ootrr
