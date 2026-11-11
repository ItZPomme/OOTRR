// Généré par ootrr/tools/menutest.py (ground_models) : ne pas modifier à la main.
#pragma once

namespace ootrr::ground {

// objet posé au sol -> fichiers de son modèle (copiés dans les archives des jetons)
struct GroundModel { const char* item; const char* model; const char* anim; };
constexpr int kGroundModelCount = 37;
inline constexpr GroundModel kGroundModels[kGroundModelCount] = {
    {"Item_Hookshot", "Component/ModelInfo/Item_Hookshot.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Item_Hookshot.engine__component__AnimationParam.bgyml"},
    {"Item_Longshot", "Component/ModelInfo/Item_Longshot.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Item_Longshot.engine__component__AnimationParam.bgyml"},
    {"Item_Scale_Silver", "Component/ModelInfo/Item_Scale_Silver.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Item_Scale_Silver.engine__component__AnimationParam.bgyml"},
    {"Item_Scale_Gold", "Component/ModelInfo/Item_Scale_Gold.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Item_Scale_Gold.engine__component__AnimationParam.bgyml"},
    {"Item_BombBag_Small", "Component/ModelInfo/Item_BombBag_Small.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Item_BombBag_Small.engine__component__AnimationParam.bgyml"},
    {"Item_BombBag_Medium", "Component/ModelInfo/Item_BombBag_Medium.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Item_BombBag_Medium.engine__component__AnimationParam.bgyml"},
    {"Item_BombBag_Large", "Component/ModelInfo/Item_BombBag_Large.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Item_BombBag_Large.engine__component__AnimationParam.bgyml"},
    {"Item_Boomerang", "Component/ModelInfo/Item_Boomerang.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Item_Boomerang.engine__component__AnimationParam.bgyml"},
    {"Item_Hammer", "Component/ModelInfo/Item_Hammer.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Item_Hammer.engine__component__AnimationParam.bgyml"},
    {"Item_DinFire", "Component/ModelInfo/Item_DinFire.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Item_DinFire.engine__component__AnimationParam.bgyml"},
    {"Item_Token_Gerudo", "Component/ModelInfo/Item_Token_Gerudo.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Item_Token_Gerudo.engine__component__AnimationParam.bgyml"},
    {"Item_ZeldaLetter", "Component/ModelInfo/Item_ZeldaLetter.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Item_ZeldaLetter.engine__component__AnimationParam.bgyml"},
    {"Item_Stone_Forest", "Component/ModelInfo/Item_Stone_Forest.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Dummy.engine__component__AnimationParam.bgyml"},
    {"Item_Stone_Fire", "Component/ModelInfo/Item_Stone_Fire.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Dummy.engine__component__AnimationParam.bgyml"},
    {"Item_Stone_Water", "Component/ModelInfo/Item_Stone_Water.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Dummy.engine__component__AnimationParam.bgyml"},
    {"Item_Medal_Forest", "Component/ModelInfo/Item_Medal_Forest.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Dummy.engine__component__AnimationParam.bgyml"},
    {"Item_Medal_Fire", "Component/ModelInfo/Item_Medal_Fire.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Dummy.engine__component__AnimationParam.bgyml"},
    {"Item_Medal_Water", "Component/ModelInfo/Item_Medal_Water.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Dummy.engine__component__AnimationParam.bgyml"},
    {"Item_Medal_Spirit", "Component/ModelInfo/Item_Medal_Spirit.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Dummy.engine__component__AnimationParam.bgyml"},
    {"Item_Medal_Shadow", "Component/ModelInfo/Item_Medal_Shadow.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Dummy.engine__component__AnimationParam.bgyml"},
    {"Item_Medal_Light", "Component/ModelInfo/Item_Medal_Light.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Dummy.engine__component__AnimationParam.bgyml"},
    {"Item_FaroreWind", "Component/ModelInfo/Item_FaroreWind.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Item_DinFire.engine__component__AnimationParam.bgyml"},
    {"Item_NayruLove", "Component/ModelInfo/Item_NayruLove.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Item_DinFire.engine__component__AnimationParam.bgyml"},
    {"Item_Wallet_Medium", "Component/ModelInfo/Item_Wallet_Medium.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Item_Wallet_Medium.engine__component__AnimationParam.bgyml"},
    {"Item_Wallet_Large", "Component/ModelInfo/Item_Wallet_Large.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Item_Wallet_Large.engine__component__AnimationParam.bgyml"},
    {"Item_Quiver_Medium", "Component/ModelInfo/Item_Quiver_Medium.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Item_Quiver_Medium.engine__component__AnimationParam.bgyml"},
    {"Item_Quiver_Large", "Component/ModelInfo/Item_Quiver_Large.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Item_Quiver_Large.engine__component__AnimationParam.bgyml"},
    {"Item_BulletBag_Medium", "Component/ModelInfo/Item_BulletBag_Medium.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Item_BulletBag_Medium.engine__component__AnimationParam.bgyml"},
    {"Item_BulletBag_Large", "Component/ModelInfo/Item_BulletBag_Large.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Item_BulletBag_Large.engine__component__AnimationParam.bgyml"},
    {"Obj_Heart_Piece", "Component/ModelInfo/Obj_Heart_Piece.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Obj_Heart_Piece.engine__component__AnimationParam.bgyml"},
    {"Obj_Heart_Container", "Component/ModelInfo/Obj_Heart_Container.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Obj_Heart_Container.engine__component__AnimationParam.bgyml"},
    {"Item_ScrubBusinessSeed", "Component/ModelInfo/Item_ScrubBusinessSeed.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Item_ScrubBusinessSeed.engine__component__AnimationParam.bgyml"},
    {"Obj_Rupee_Green", "Component/ModelInfo/Obj_Rupee_Green.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Obj_Rupee.engine__component__AnimationParam.bgyml"},
    {"Obj_Rupee_Blue", "Component/ModelInfo/Obj_Rupee_Blue.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Obj_Rupee.engine__component__AnimationParam.bgyml"},
    {"Obj_Rupee_Red", "Component/ModelInfo/Obj_Rupee_Red.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Obj_Rupee.engine__component__AnimationParam.bgyml"},
    {"Obj_Rupee_Purple", "Component/ModelInfo/Obj_Rupee_Purple.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Obj_Rupee.engine__component__AnimationParam.bgyml"},
    {"Obj_Rupee_Gold", "Component/ModelInfo/Obj_Rupee_Gold.engine__component__ModelInfo.bgyml", "Component/AnimationParam/Obj_Rupee.engine__component__AnimationParam.bgyml"},
};

}  // namespace ootrr::ground
