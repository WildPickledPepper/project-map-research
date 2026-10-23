#pragma once
#include <memory>
#include <map>
namespace alpha {
class Store {
public:
    virtual bool query(int key) = 0;
    virtual bool query(const char* key) = 0;
};
class Live : public Store {
public:
    bool query(int key) override;
    bool query(const char* key) override;
};
class CacheGuard { public: int get() { return 1; } };
bool consume(Store& db) { return db.query(1); }
bool consumeOwned(std::unique_ptr<Store> db) { return db.get()->query(1); }
}
namespace beta {
class Store { public: bool query(int key) { return key > 0; } };
bool consume(Store& db) { return db.query(2); }
}
